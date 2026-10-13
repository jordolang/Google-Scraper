#!/usr/bin/env python3
"""Fallback contact lookup for businesses whose website yielded nothing.

The contact scraper only sees what a business publishes on its own site — and
plenty of small businesses publish nothing at all (or have no site).  We still
know the name and the address from the Maps listing, which is enough to look
the business up elsewhere: Yellow Pages, the BBB, search-engine snippets and
the business's Facebook page.

:meth:`PhoneLookup.find_contacts` fills in whichever of phone and email is
missing, and says where each came from::

    with PhoneLookup() as lookup:
        result = lookup.find_contacts("Bright Spark Electric", "Columbus, OH")
        result["phones"], result["phone_source"]   # ['(614) 555-0142'], 'yellowpages'
        result["emails"], result["email_source"]   # ['info@brightspark.com'], 'duckduckgo'

:meth:`PhoneLookup.find` is the older phone-only lookup the TUI's "find
phone" action still uses.
"""

from __future__ import annotations

import os
import re
import time
from difflib import SequenceMatcher
from urllib.parse import quote_plus, urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

#: The phone-only lookup sources, in the order they are tried.
SOURCES = ("google", "yellowpages")

#: The sources :meth:`PhoneLookup.find_contacts` tries, in order. Directories
#: first, because they tie a number to one named listing; search snippets
#: after, because they are broader but noisier; Google last, because it is
#: the most likely to answer an automated browser with a captcha.
CONTACT_SOURCES = ("yellowpages", "bbb", "duckduckgo", "facebook", "google")

#: What each source is called wherever a person reads it.
SOURCE_LABELS = {
    "": "website",
    "website": "website",
    "maps": "Google Maps",
    "yellowpages": "Yellow Pages",
    "bbb": "BBB",
    "duckduckgo": "web search",
    "facebook": "Facebook",
    "google": "Google",
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")

#: Addresses on these domains belong to the site that listed the business,
#: a template, or a tracking service — never to the business itself.
_BLOCKED_EMAIL_DOMAINS = (
    "yellowpages.com", "yp.com", "bbb.org", "facebook.com", "fb.com",
    "google.com", "duckduckgo.com", "yelp.com", "example.com", "example.org",
    "sentry.io", "wixpress.com", "wix.com", "squarespace.com", "godaddy.com",
    "domain.com", "email.com", "yourdomain.com", "sentry-next.wixpress.com",
    "angi.com", "homeadvisor.com", "thumbtack.com", "mapquest.com",
)

#: Personal mailbox providers. Plenty of small businesses use one, so an
#: address here counts when it sits in a snippet that names the business.
_FREEMAIL_DOMAINS = (
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "me.com", "live.com", "msn.com", "comcast.net",
    "att.net", "sbcglobal.net", "verizon.net", "bellsouth.net", "ymail.com",
    "protonmail.com", "proton.me", "mail.com", "charter.net", "cox.net",
)

#: Words that say nothing about which business a name refers to.
_NAME_NOISE = {
    "the", "and", "of", "llc", "inc", "co", "company", "corp", "corporation",
    "ltd", "services", "service", "group", "pllc", "pc", "dba",
}

_PHONE_RE = re.compile(r"\(?\b([2-9]\d{2})\)?[-.\s]?([2-9]\d{2})[-.\s]?(\d{4})\b")
# Numbers that are placeholders, or belong to the site rather than the business.
_BAD_PREFIXES = ("800", "888", "877", "866", "855", "844", "833")


def normalize(raw: str) -> str | None:
    """Return ``(614) 555-0142`` for anything phone-shaped, else ``None``."""
    match = _PHONE_RE.search(str(raw or ""))
    if not match:
        return None
    area, exchange, line = match.groups()
    if len({*area, *exchange, *line}) == 1:  # 111-111-1111 and friends
        return None
    return f"({area}) {exchange}-{line}"


def extract_phones(text: str, limit: int = 3, allow_tollfree: bool = False) -> list[str]:
    """Pull distinct, plausible local phone numbers out of a blob of text."""
    found: list[str] = []
    for match in _PHONE_RE.finditer(str(text or "")):
        number = normalize(match.group(0))
        if not number or number in found:
            continue
        if not allow_tollfree and match.group(1) in _BAD_PREFIXES:
            continue
        found.append(number)
        if len(found) >= limit:
            break
    return found


def extract_emails(text: str) -> list[str]:
    """Distinct, lower-cased email addresses in ``text``, blocked domains dropped."""
    found: list[str] = []
    for match in _EMAIL_RE.finditer(str(text or "")):
        email = match.group(0).strip(".").lower()
        domain = email.rsplit("@", 1)[-1]
        if domain.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
            continue
        if any(domain == d or domain.endswith("." + d) for d in _BLOCKED_EMAIL_DOMAINS):
            continue
        if email not in found:
            found.append(email)
    return found


def name_tokens(name: str) -> list[str]:
    """The words in a business name that tell it apart from its neighbours."""
    words = re.findall(r"[a-z0-9]+", str(name or "").lower())
    return [w for w in words if w not in _NAME_NOISE and len(w) >= 3]


def mentions_business(text: str, name: str) -> bool:
    """True when ``text`` names the business: at least half its distinctive words."""
    tokens = name_tokens(name)
    if not tokens:
        return False
    haystack = str(text or "").lower()
    hits = sum(1 for token in tokens if token in haystack)
    return hits * 2 >= len(tokens)


def same_business(found: str, wanted: str) -> bool:
    """True when a directory listing's name is the business we searched for."""
    a = " ".join(name_tokens(found))
    b = " ".join(name_tokens(wanted))
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.75


def site_domain(website: str) -> str:
    """``https://www.brightspark.com/contact`` -> ``brightspark.com``."""
    if not website:
        return ""
    url = website if "://" in website else f"http://{website}"
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def plausible_email(email: str, name: str, website: str = "",
                    allow_freemail: bool = True) -> bool:
    """Whether an address found off-site really belongs to this business.

    Accepted when it is on the business's own domain, on a domain built from
    its name (``brightsparkelectric.com``), or, when ``allow_freemail``, at a
    personal mailbox provider. Anything else is somebody else's address.
    """
    domain = email.rsplit("@", 1)[-1].lower()
    own = site_domain(website)
    if own and (domain == own or domain.endswith("." + own)):
        return True
    label = domain.split(".")[0]
    if any(len(token) >= 4 and token in label for token in name_tokens(name)):
        return True
    return allow_freemail and domain in _FREEMAIL_DOMAINS


def city_state(address: str) -> str:
    """``123 Main St, Columbus, OH 43215`` -> ``Columbus, OH``; else the input."""
    match = re.search(r"([A-Za-z][A-Za-z .'-]+),\s*([A-Z]{2})\b(?:\s+\d{5})?",
                      str(address or ""))
    if not match:
        return str(address or "").strip()
    city = match.group(1).split(",")[-1].strip()
    return f"{city}, {match.group(2)}"


def _empty() -> dict:
    return {"phones": [], "emails": []}


class PhoneLookup:
    """Looks a business up off its own website for a phone number and email."""

    def __init__(self, headless: bool = True, page_timeout: int = 20) -> None:
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Drive the browser the app bundled, when it unpacked one; falls back
        # to whatever Chrome is installed otherwise.
        bundled = os.environ.get("LLSP_CHROME_BINARY")
        if bundled:
            options.binary_location = bundled

        # Hand Selenium the driver that shipped with the browser. Without an
        # explicit service it runs Selenium Manager, which goes to the network
        # — and publishes no driver at all for ARM64 Windows.
        driver_path = os.environ.get("LLSP_CHROMEDRIVER")
        service = None
        if driver_path:
            from selenium.webdriver.chrome.service import Service

            service = Service(driver_path)

        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(page_timeout)

    # -- sources -------------------------------------------------------------
    def google(self, name: str, location: str = "") -> list[str]:
        """Phone numbers from a Google results page (knowledge panel included)."""
        query = quote_plus(f"{name} {location} phone number".strip())
        return self._phones_from(f"https://www.google.com/search?q={query}")

    def yellowpages(self, name: str, location: str = "") -> list[str]:
        """Phone numbers from a Yellow Pages search."""
        url = (
            "https://www.yellowpages.com/search"
            f"?search_terms={quote_plus(name)}&geo_location_terms={quote_plus(location)}"
        )
        # Yellow Pages puts the number in a dedicated element; prefer it over a
        # blind text regex, which would happily grab an unrelated listing.
        phones = self._phones_from_elements(url, "div.phones, .phone, .phones")
        return phones or self._phones_from(url, navigate=False)

    # -- contact sources -----------------------------------------------------
    # Each returns {"phones": [...], "emails": [...]} for one business, and
    # only from listings or snippets that name that business.
    def _yellowpages_contacts(self, name: str, location: str, website: str) -> dict:
        url = (
            "https://www.yellowpages.com/search"
            f"?search_terms={quote_plus(name)}&geo_location_terms={quote_plus(location)}"
        )
        if not self._load(url):
            return _empty()
        found = _empty()
        detail = ""
        for card in self._elements("div.result, div.search-results .v-card")[:10]:
            title = self._first_text(card, "a.business-name, .business-name")
            if not same_business(title, name):
                continue
            found["phones"] = extract_phones(self._first_text(card, ".phones, .phone"))
            detail = self._first_attr(card, "a.business-name", "href")
            break
        if detail:
            # The email is only on the listing's own page, behind "Email Business".
            if self._load(urljoin("https://www.yellowpages.com", detail)):
                for link in self._elements("a.email-business, a[href^='mailto:']"):
                    href = self._attr(link, "href")
                    for email in extract_emails(href.replace("mailto:", " ")):
                        if plausible_email(email, name, website):
                            found["emails"].append(email)
                if not found["phones"]:
                    found["phones"] = extract_phones(self._first_text(
                        None, ".phone, .phones, a[href^='tel:']"))
        return found

    def _bbb_contacts(self, name: str, location: str, website: str) -> dict:
        url = (
            "https://www.bbb.org/search?find_country=USA"
            f"&find_text={quote_plus(name)}&find_loc={quote_plus(location)}"
        )
        if not self._load(url):
            return _empty()
        for card in self._elements("div.result-card, .card.result-card, "
                                   "div[class*='result-item']")[:10]:
            title = self._first_text(card, "h3, .result-business-name, a")
            if not same_business(title, name):
                continue
            text = self._text(card)
            emails = [e for e in extract_emails(text) if plausible_email(e, name, website)]
            return {"phones": extract_phones(text), "emails": emails}
        return _empty()

    def _search_snippets(self, query: str, name: str, website: str,
                         source: str) -> dict:
        """Phones and emails from DuckDuckGo results that name the business."""
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        if not self._load(url):
            return _empty()
        found = _empty()
        for result in self._elements("div.result, .result__body")[:10]:
            text = self._text(result)
            if not mentions_business(text, name):
                continue
            for phone in extract_phones(text):
                if phone not in found["phones"]:
                    found["phones"].append(phone)
            for email in extract_emails(text):
                if plausible_email(email, name, website) and email not in found["emails"]:
                    found["emails"].append(email)
        return found

    def _duckduckgo_contacts(self, name: str, location: str, website: str) -> dict:
        return self._search_snippets(f'"{name}" {location} email phone',
                                     name, website, "duckduckgo")

    def _facebook_contacts(self, name: str, location: str, website: str) -> dict:
        # Facebook pages show the email and phone in their intro, which the
        # search engine quotes — so the page never has to be opened (and its
        # login wall never met).
        return self._search_snippets(f'"{name}" {location} site:facebook.com',
                                     name, website, "facebook")

    def _google_contacts(self, name: str, location: str, website: str) -> dict:
        query = quote_plus(f'"{name}" {location} phone email'.strip())
        if not self._load(f"https://www.google.com/search?q={query}"):
            return _empty()
        text = self._page_text()
        if not mentions_business(text, name):
            return _empty()
        # The whole page, not one snippet: only an address on the business's
        # own or name-built domain is trusted here.
        emails = [e for e in extract_emails(text)
                  if plausible_email(e, name, website, allow_freemail=False)]
        return {"phones": extract_phones(text), "emails": emails}

    # -- driving -------------------------------------------------------------
    def _load(self, url: str) -> bool:
        try:
            self.driver.get(url)
            time.sleep(2)
            return True
        except (TimeoutException, WebDriverException) as exc:
            print(f"    lookup failed for {url}: {str(exc)[:80]}")
            return False

    def _page_text(self) -> str:
        try:
            return self.driver.find_element(By.TAG_NAME, "body").text
        except WebDriverException:
            return ""

    def _elements(self, selector: str, root=None) -> list:
        try:
            return list((root or self.driver).find_elements(By.CSS_SELECTOR, selector))
        except WebDriverException:
            return []

    @staticmethod
    def _text(element) -> str:
        try:
            return element.text or ""
        except WebDriverException:
            return ""

    @staticmethod
    def _attr(element, attribute: str) -> str:
        try:
            return element.get_attribute(attribute) or ""
        except WebDriverException:
            return ""

    def _first_text(self, root, selector: str) -> str:
        found = self._elements(selector, root)
        return self._text(found[0]) if found else ""

    def _first_attr(self, root, selector: str, attribute: str) -> str:
        found = self._elements(selector, root)
        return self._attr(found[0], attribute) if found else ""

    def _phones_from(self, url: str, navigate: bool = True) -> list[str]:
        if navigate and not self._load(url):
            return []
        return extract_phones(self._page_text())

    def _phones_from_elements(self, url: str, selector: str) -> list[str]:
        if not self._load(url):
            return []
        phones: list[str] = []
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            return []
        for element in elements[:5]:
            try:
                number = normalize(element.text)
            except WebDriverException:
                continue
            if number and number not in phones:
                phones.append(number)
        return phones

    # -- api -----------------------------------------------------------------
    def find(self, name: str, location: str = "", sources=SOURCES) -> dict:
        """Look ``name`` up on each source until one yields a number.

        Returns ``{"phones": [...], "source": "google" | "yellowpages" | ""}``.
        """
        if not name:
            return {"phones": [], "source": ""}
        for source in sources:
            finder = getattr(self, source, None)
            if finder is None:
                continue
            phones = finder(name, location)
            if phones:
                return {"phones": phones, "source": source}
        return {"phones": [], "source": ""}

    def find_contacts(self, name: str, location: str = "", *, website: str = "",
                      need_phone: bool = True, need_email: bool = True,
                      sources=CONTACT_SOURCES) -> dict:
        """Fill in whichever of phone and email is missing, source by source.

        Stops as soon as everything asked for has been found. Returns
        ``{"phones", "phone_source", "emails", "email_source"}``; a source is
        "" when nothing was found for that field.
        """
        result = {"phones": [], "phone_source": "", "emails": [], "email_source": ""}
        if not name:
            return result
        for source in sources:
            want_phone = need_phone and not result["phones"]
            want_email = need_email and not result["emails"]
            if not (want_phone or want_email):
                break
            finder = getattr(self, f"_{source}_contacts", None)
            if finder is None:
                continue
            try:
                found = finder(name, location, website)
            except WebDriverException as exc:
                print(f"    {source} lookup failed: {str(exc)[:80]}")
                continue
            if want_phone and found.get("phones"):
                result["phones"] = list(found["phones"])[:3]
                result["phone_source"] = source
            if want_email and found.get("emails"):
                result["emails"] = list(found["emails"])[:3]
                result["email_source"] = source
        return result

    def close(self) -> None:
        try:
            self.driver.quit()
        except WebDriverException:  # pragma: no cover - already gone
            pass

    def __enter__(self) -> "PhoneLookup":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


#: The same class under the name that says what it does now.
ContactLookup = PhoneLookup
