#!/usr/bin/env python3
"""Fallback phone lookup for businesses whose website yielded nothing.

The contact scraper only sees what a business publishes on its own site — and
plenty of small businesses publish nothing at all (or have no site).  We still
know the name and the address from the Maps listing, which is enough to look
the phone number up on Google or Yellow Pages.

Used by the TUI's "find phone" action and importable on its own::

    with PhoneLookup() as lookup:
        result = lookup.find("Bright Spark Electric", "Columbus, OH")
        result["phones"]   # ['(614) 555-0142']
        result["source"]   # 'google'
"""

from __future__ import annotations

import re
import time
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

#: The lookup sources, in the order they are tried.
SOURCES = ("google", "yellowpages")

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


class PhoneLookup:
    """Searches Google and Yellow Pages for a business's phone number."""

    def __init__(self, headless: bool = True, page_timeout: int = 20) -> None:
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(options=options)
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

    def close(self) -> None:
        try:
            self.driver.quit()
        except WebDriverException:  # pragma: no cover - already gone
            pass

    def __enter__(self) -> "PhoneLookup":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
