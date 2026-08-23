#!/usr/bin/env python3
"""
Google Maps Business Scraper
Scrapes business information including names, addresses, phone numbers, websites, etc.

Two sources are merged for every business:

1. The **search-result card** in the left-hand feed, which always carries the
   name, rating, category and — crucially — the phone number.
2. The **place detail page**, which adds the full address, website, plus code
   and opening hours.

The detail panel routinely hydrates only halfway when it is opened by direct
URL navigation, so the card is what keeps the phone column full even when the
panel comes up empty.
"""

import os
import time
import csv
import json
import re
from pathlib import Path

import data_store
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import argparse


#: Google renders each detail row with a leading Material-icon glyph from the
#: Unicode private-use area (U+E0B0 for the phone, U+E0C8 for the
#: address...).  Reading ``element.text`` therefore yields ``"\n(740)
#: 453-3649"`` — a value that looks like a phone number to a human squinting at
#: a CSV but breaks every downstream consumer that renders or matches it.
_ICON_RE = re.compile("[\ue000-\uf8ff]")

#: North-American numbers as they appear on Maps: "(740) 453-3649".
_PHONE_RE = re.compile("\\+?\\d[\\d\\s().\u2011-]{7,}\\d")


def clean_text(value: str) -> str:
    """Strip Material-icon glyphs and collapse whitespace to a single line."""
    text = _ICON_RE.sub(" ", str(value or ""))
    # Maps uses a narrow no-break space in hours and a non-breaking
    # hyphen in some numbers; normalise both to their ASCII forms.
    text = text.replace("\u202f", " ").replace("\u2011", "-")
    return re.sub(r"\s+", " ", text).strip()


def parse_phone(raw: str) -> tuple:
    """Return ``(display, e164)`` for a phone-shaped string, else ``("", "")``.

    ``"\\ue0b0\\n(740) 453-3649"`` -> ``("(740) 453-3649", "+17404533649")``
    and ``"phone:tel:+17404533649"`` -> the same pair, so the ``data-item-id``
    attribute can be fed straight in.
    """
    text = clean_text(raw)
    if not text:
        return "", ""
    match = _PHONE_RE.search(text)
    if not match:
        return "", ""
    digits = re.sub(r"\D", "", match.group(0))
    plus = match.group(0).lstrip().startswith("+")

    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10 and digits[0] not in "01" and digits[3] not in "01":
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}", f"+1{digits}"
    if plus and 8 <= len(digits) <= 15:  # international listing; keep verbatim
        return clean_text(match.group(0)), f"+{digits}"
    return "", ""


def _label_value(aria_label: str, label: str) -> str:
    """Pull the value out of an aria-label like ``"Phone: (740) 453-3649"``."""
    text = clean_text(aria_label)
    prefix = f"{label}:"
    if text.lower().startswith(prefix.lower()):
        text = text[len(prefix):]
    return text.strip()


class GoogleMapsScraper:
    def __init__(self, headless=True, wait_seconds=15):
        """Initialize the scraper with Chrome options"""
        options = webdriver.ChromeOptions()
        if headless:
            # The new headless mode renders the results feed the same way the
            # visible browser does; the legacy one served a stripped-down page.
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        # A real-sized viewport: the feed renders fewer cards in a small one.
        options.add_argument('--window-size=1440,1200')
        # Pin the language — every field below is read out of an English
        # aria-label ("Phone: …", "Address: …"), so a localized UI would
        # silently empty those columns.
        options.add_argument('--lang=en-US')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option('prefs', {'intl.accept_languages': 'en-US,en'})

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
        self.driver.set_window_size(1440, 1200)
        self.wait = WebDriverWait(self.driver, wait_seconds)
        self.businesses = []
        self.search_term = ""
        self.location = ""
        #: place URL -> facts harvested from that business's feed card.
        self._cards = {}

    # ------------------------------------------------------------------ search

    def search(self, search_term, location="", max_scrolls=10):
        """Search for businesses on Google Maps"""
        # Remember the seed query so each record knows its local-search origin.
        self.search_term = search_term
        self.location = location
        query = f"{search_term} {location}".strip()
        # hl/gl pin the result language and region to match the aria-label
        # parsing above, regardless of where the machine running this sits.
        url = (
            "https://www.google.com/maps/search/"
            f"{query.replace(' ', '+')}?hl=en&gl=us"
        )

        print(f"Searching for: {query}")
        self.driver.get(url)
        self._dismiss_consent()
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div[role="feed"]')
            ))
        except TimeoutException:
            print("Results feed did not appear")
            return

        # Scroll to load more results
        self._scroll_results(max_scrolls)

    def _dismiss_consent(self):
        """Click through the cookie/consent interstitial if one is shown."""
        for selector in (
            'button[aria-label*="Accept all" i]',
            'button[aria-label*="Reject all" i]',
            'form[action*="consent"] button',
        ):
            try:
                button = self.driver.find_element(By.CSS_SELECTOR, selector)
            except NoSuchElementException:
                continue
            try:
                self.driver.execute_script("arguments[0].click();", button)
                time.sleep(2)
                return True
            except Exception:
                continue
        return False

    def _scroll_results(self, max_scrolls=10):
        """Scroll the results panel until Maps stops loading new businesses.

        Stops early on the "end of the list" marker or once the feed height
        holds steady, so a small town does not cost ten pointless sleeps.
        """
        try:
            scrollable_div = self.driver.find_element(By.CSS_SELECTOR,
                'div[role="feed"]')
        except NoSuchElementException:
            print("Could not find scrollable results")
            return

        last_height = 0
        stagnant = 0
        for i in range(max_scrolls):
            self.driver.execute_script(
                'arguments[0].scrollTop = arguments[0].scrollHeight',
                scrollable_div
            )
            time.sleep(2)

            cards = len(self.driver.find_elements(By.CSS_SELECTOR, _CARD_SELECTOR))
            print(f"Scrolled {i+1}/{max_scrolls} ({cards} listings loaded)")

            if self._reached_end_of_list():
                print("Reached the end of the results list")
                break

            height = self.driver.execute_script(
                'return arguments[0].scrollHeight', scrollable_div)
            stagnant = stagnant + 1 if height == last_height else 0
            last_height = height
            if stagnant >= 2:
                print("No further results loading")
                break

    def _reached_end_of_list(self):
        """True once Maps shows its end-of-results marker."""
        try:
            return bool(self.driver.find_elements(
                By.XPATH,
                "//span[contains(., \"reached the end of the list\")]",
            ))
        except Exception:
            return False

    # ------------------------------------------------------- card harvesting

    def _harvest_cards(self):
        """Read every result card in the feed into ``self._cards``.

        The card is the reliable source for the phone number: it is rendered
        with the list and never depends on the detail panel hydrating.  Card
        text looks like::

            Precision Roofing & Gutters
            5.0
            Roofing contractor · 2333 Adamsville Rd
            Open 24 hours · (740) 453-3649
        """
        for card in self.driver.find_elements(By.CSS_SELECTOR, _CARD_SELECTOR):
            try:
                link = card.find_element(
                    By.CSS_SELECTOR, 'a[href*="/maps/place"]')
                url = link.get_attribute('href')
                if not url:
                    continue
                facts = self._parse_card(card, link)
                # Keep the richest version if a card re-renders while scrolling.
                previous = self._cards.get(url, {})
                merged = {**previous, **{k: v for k, v in facts.items() if v}}
                self._cards[url] = merged
            except (StaleElementReferenceException, NoSuchElementException):
                continue
            except Exception:
                continue
        return self._cards

    @staticmethod
    def _card_rating(card):
        """Return ``(rating, reviews_count)`` from a card's rating widget.

        The widget is ``<span role="img" aria-label="5.0 stars">5.0</span>``
        optionally followed by ``<span>(127)</span>``.  Scoping to it matters:
        a bare parenthesised-number search over the card text happily returns
        the phone number's area code instead.
        """
        rating, reviews = "", ""
        for el in card.find_elements(By.CSS_SELECTOR, 'span[role="img"][aria-label]'):
            try:
                label = clean_text(el.get_attribute("aria-label"))
            except StaleElementReferenceException:
                continue
            match = re.match(r"^(\d(?:\.\d)?)\s+stars?\b", label)
            if not match:
                continue
            rating = match.group(1)
            # The count sits beside the widget, inside the same wrapper.
            try:
                wrapper = el.find_element(By.XPATH, "./..")
                found = re.search(r"\((\d[\d,]*)\)", clean_text(wrapper.text))
                if found:
                    reviews = found.group(1).replace(",", "")
                if not reviews:
                    count = re.search(r"([\d,]+)\s+reviews?\b", label)
                    if count:
                        reviews = count.group(1).replace(",", "")
            except (NoSuchElementException, StaleElementReferenceException):
                pass
            break
        return rating, reviews

    def _parse_card(self, card, link):
        """Pull name / rating / reviews / category / phone out of one card."""
        facts = {"name": "", "rating": "", "reviews_count": "",
                 "category": "", "address": "", "phone": "", "phone_e164": ""}

        facts["name"] = clean_text(link.get_attribute("aria-label"))
        text = clean_text(card.text)

        # Rating + review count. Both are read from the rating widget only --
        # never from the card text at large, where "(740) 453-3649" would be
        # mistaken for a "(740)" review count.
        facts["rating"], facts["reviews_count"] = self._card_rating(card)

        # Maps gives the card's phone number its own span; regexing the card
        # text is only the fallback for when that class name changes.
        try:
            facts["phone"], facts["phone_e164"] = parse_phone(
                card.find_element(By.CSS_SELECTOR, "span.UsdlK").text)
        except (NoSuchElementException, StaleElementReferenceException):
            pass
        if not facts["phone"]:
            facts["phone"], facts["phone_e164"] = parse_phone(text)

        # "Roofing contractor · 2333 Adamsville Rd" — category then address.
        for line in card.text.splitlines():
            line = clean_text(line)
            if "·" not in line or _PHONE_RE.search(line):
                continue
            parts = [p.strip() for p in line.split("·") if p.strip()]
            if parts and not facts["category"]:
                facts["category"] = parts[0]
            if len(parts) > 1 and not facts["address"]:
                facts["address"] = parts[-1]
            break

        return facts

    # ----------------------------------------------------------- the main loop

    def scrape_listings(self, progress=None):
        """Scrape all visible business listings.

        ``progress`` is an optional ``callable(str)`` used by the TUI to stream
        status lines while the scrape runs.
        """
        def emit(message):
            print(message)
            if progress:
                progress(message)

        try:
            # Wait for results to load
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div[role="feed"]')
            ))

            # Read the cards *before* navigating away — once we open a place
            # page the feed is gone, and with it the guaranteed phone number.
            self._harvest_cards()

            # Collect all business URLs first (more stable than working with elements)
            business_urls = self._collect_all_business_urls()

            emit(f"Found {len(business_urls)} businesses")

            # Process each business by URL
            for idx, url in enumerate(business_urls):
                card = self._cards.get(url, {})
                try:
                    # Extract business details, falling back to the card.
                    business_data = self._scrape_one(url, card)
                    if business_data:
                        self.businesses.append(business_data)
                        emit(f"[{idx+1}/{len(business_urls)}] "
                             f"{business_data.get('name') or 'business'} "
                             f"— {business_data.get('phone') or 'no phone'}")

                except Exception as e:
                    emit(f"[{idx+1}/{len(business_urls)}] error: {str(e)[:80]}")
                    continue

        except TimeoutException:
            emit("Timeout waiting for results")

    def _scrape_one(self, url, card, attempts=2):
        """Open one place page and extract it, retrying a half-loaded panel."""
        for attempt in range(attempts):
            self.driver.get(url)
            try:
                # The name is the last thing to render before the detail rows,
                # so waiting on it beats a blind sleep.
                self.wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'h1.DUwDvf')))
                time.sleep(1)
                return self._extract_business_details(card)
            except TimeoutException:
                if attempt + 1 < attempts:
                    continue

        # The panel never hydrated. The card still knows the name and the
        # phone, which is the whole point of harvesting it — emit that rather
        # than dropping the business.
        if card:
            data = self._blank_record()
            data.update({k: v for k, v in card.items() if v})
            data["url"] = url
            return data
        return None

    def _blank_record(self):
        """An empty row with every listing column present, in order."""
        data = {field: "" for field in data_store.LISTING_FIELDS}
        data["search_term"] = self.search_term
        data["search_location"] = self.location
        return data

    def _collect_all_business_urls(self):
        """Collect all unique business URLs from the search results"""
        urls = []
        seen = set()
        retries = 0
        max_retries = 3

        while retries < max_retries:
            try:
                links = self.driver.find_elements(By.CSS_SELECTOR,
                    'a[href^="https://www.google.com/maps/place"]')

                new_urls = 0
                for link in links:
                    try:
                        href = link.get_attribute('href')
                        if href and href not in seen:
                            seen.add(href)
                            # Keep Maps' own ranking order — it is the local-SEO
                            # ordering the outreach is built around.
                            urls.append(href)
                            new_urls += 1
                    except StaleElementReferenceException:
                        continue
                    except Exception:
                        continue

                # If we found new URLs, reset retry counter
                if new_urls > 0:
                    retries = 0
                else:
                    retries += 1

                time.sleep(0.5)

            except Exception as e:
                retries += 1
                time.sleep(1)

        return urls

    # ------------------------------------------------------ detail extraction

    def _detail_row(self, selector, label):
        """Read one detail row (phone, address, plus code…).

        Prefers the ``aria-label`` — ``"Phone: (740) 453-3649"`` — because the
        visible text is prefixed with a private-use icon glyph and a newline.
        """
        try:
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            return "", None
        try:
            value = _label_value(element.get_attribute("aria-label") or "", label)
            return (value or clean_text(element.text)), element
        except StaleElementReferenceException:
            return "", None

    def _extract_phone(self):
        """Return ``(display, e164)`` for the listing's phone number.

        Tries hardest here, because the phone is the single most valuable
        column: the ``data-item-id`` attribute (``phone:tel:+17404533649``) is
        the most reliable source, then the aria-label, then the icon-prefixed
        visible text.
        """
        try:
            element = self.driver.find_element(
                By.CSS_SELECTOR, 'button[data-item-id^="phone"]')
        except NoSuchElementException:
            return "", ""

        for source in (
            element.get_attribute("data-item-id"),   # phone:tel:+17404533649
            element.get_attribute("aria-label"),     # Phone: (740) 453-3649
            element.text,                            # \n(740) 453-3649
        ):
            display, e164 = parse_phone(source or "")
            if display:
                return display, e164
        return "", ""

    def _extract_hours(self):
        """Return the opening hours as ``"Mon: 8 AM–5 PM; Tue: …"``.

        The old ``button[data-item-id="oh"]`` selector no longer exists, which
        is why this column was empty on every export.  Maps now renders an
        hours block keyed by ``jsaction`` with one aria-labelled row per day.
        """
        # Expand the week if it is collapsed behind the summary chevron.
        try:
            toggle = self.driver.find_element(
                By.CSS_SELECTOR, '[aria-label*="Show open hours for the week" i]')
            self.driver.execute_script("arguments[0].click();", toggle)
            time.sleep(1)
        except (NoSuchElementException, StaleElementReferenceException):
            pass
        except Exception:
            pass

        days = []
        for el in self.driver.find_elements(
                By.CSS_SELECTOR, '[aria-label*="Copy open hours" i]'):
            try:
                label = clean_text(el.get_attribute("aria-label"))
            except StaleElementReferenceException:
                continue
            # "Saturday, Open 24 hours, Copy open hours"
            parts = [p.strip() for p in label.split(",")]
            parts = [p for p in parts if p and "copy open hours" not in p.lower()]
            if len(parts) >= 2:
                entry = f"{parts[0]}: {' '.join(parts[1:])}"
                if entry not in days:
                    days.append(entry)
        if days:
            return "; ".join(days)

        # Fall back to the one-line summary ("Open 24 hours", "Closes 5 PM").
        for el in self.driver.find_elements(
                By.CSS_SELECTOR, '[jsaction*="openhours" i]'):
            try:
                summary = clean_text(el.text)
            except StaleElementReferenceException:
                continue
            if summary:
                return summary
        return ""

    def _extract_rating_reviews(self):
        """Extract (rating, reviews_count) using several fallback strategies.

        Google Maps renders these as e.g. "4.9(127)" inside div.F7nice, or in
        aria-labels like "4.9 stars" / "127 reviews". We try structured
        selectors first, then regex the block text so a DOM tweak can't zero
        us out.
        """
        rating, reviews = "", ""
        paren_re = re.compile(r"^\(\s*([\d,]+)\s*\)$")  # e.g. "(94)" / "(1,234)"

        # --- Rating: the aria-hidden span inside the F7nice block ---
        try:
            block = self.driver.find_element(By.CSS_SELECTOR, "div.F7nice")
        except NoSuchElementException:
            block = None
        if block is not None:
            try:
                rating = block.find_element(
                    By.CSS_SELECTOR, 'span[aria-hidden="true"]'
                ).text.strip()
            except NoSuchElementException:
                m = re.search(r"\d+\.\d+", block.text)
                rating = m.group(0) if m else ""
            if not rating:
                # "4.9 stars" on the star-graphic's aria-label.
                for el in block.find_elements(By.CSS_SELECTOR, '[aria-label]'):
                    m = re.match(r"^(\d(?:\.\d)?) stars?\b",
                                 clean_text(el.get_attribute("aria-label")))
                    if m:
                        rating = m.group(1)
                        break

        # --- Reviews: the count renders as a "(N)" span near the rating, and
        #     sometimes as an "N reviews" aria-label. Class names are obfuscated
        #     and change, so match by shape, scoped to the rating container. ---
        def _digits_from_paren_spans(scope):
            for span in scope.find_elements(By.TAG_NAME, "span"):
                try:
                    m = paren_re.match(span.text.strip())
                except StaleElementReferenceException:
                    continue
                if m:
                    return re.sub(r"[^\d]", "", m.group(1))
            return ""

        # 1) Look right around the rating block (its parent container).
        if not reviews and block is not None:
            try:
                container = block.find_element(By.XPATH, "./..")
                reviews = _digits_from_paren_spans(container)
            except (NoSuchElementException, StaleElementReferenceException):
                pass

        # 2) An aria-label like "123 reviews" anywhere in the header.
        if not reviews:
            for el in self.driver.find_elements(By.CSS_SELECTOR, "[aria-label*='review' i]"):
                label = el.get_attribute("aria-label") or ""
                m = re.search(r"([\d,]+)\s*review", label, re.IGNORECASE)
                if m:
                    reviews = re.sub(r"[^\d]", "", m.group(1))
                    break

        # 3) The "N reviews" tab in the place header. Scoped to the header --
        #    sweeping every span on the page is slow and invites false hits.
        if not reviews:
            for el in self.driver.find_elements(
                    By.CSS_SELECTOR, 'div[role="main"] button, div[role="main"] span'):
                try:
                    m = re.match(r"^([\d,]+)\s+reviews?$", clean_text(el.text), re.I)
                except StaleElementReferenceException:
                    continue
                if m:
                    reviews = m.group(1).replace(",", "")
                    break

        # 4) Last resort: the known (current) count span class.
        if not reviews:
            try:
                txt = self.driver.find_element(By.CSS_SELECTOR, "span.UY7F9").text.strip()
                m = paren_re.match(txt) or re.search(r"([\d,]+)", txt)
                if m:
                    reviews = re.sub(r"[^\d]", "", m.group(1))
            except NoSuchElementException:
                pass

        return rating, reviews

    def _extract_business_details(self, card=None):
        """Extract details from a business listing page.

        ``card`` is this business's row from the search feed; every field falls
        back to it, so a detail panel that renders only halfway still yields a
        usable record.
        """
        card = card or {}
        data = self._blank_record()

        try:
            # Business name
            try:
                data['name'] = clean_text(self.driver.find_element(
                    By.CSS_SELECTOR, 'h1.DUwDvf').text)
            except NoSuchElementException:
                data['name'] = ''

            # Rating + number of reviews (robust, multi-strategy)
            rating, reviews_count = self._extract_rating_reviews()
            data['rating'] = rating
            data['reviews_count'] = reviews_count

            # Category
            try:
                data['category'] = clean_text(self.driver.find_element(
                    By.CSS_SELECTOR, 'button.DkEaL').text)
            except NoSuchElementException:
                data['category'] = ''

            # Address
            data['address'], _ = self._detail_row(
                'button[data-item-id="address"]', 'Address')

            # Phone — the column this scraper exists for.
            data['phone'], data['phone_e164'] = self._extract_phone()

            # Website
            try:
                data['website'] = self.driver.find_element(By.CSS_SELECTOR,
                    'a[data-item-id="authority"]').get_attribute('href') or ''
            except NoSuchElementException:
                data['website'] = ''

            # Plus Code
            data['plus_code'], _ = self._detail_row(
                'button[data-item-id="oloc"]', 'Plus code')

            # Hours
            data['hours'] = self._extract_hours()

            # URL
            data['url'] = self.driver.current_url

            # Anything the panel failed to render, take from the feed card.
            for key, value in card.items():
                if value and not data.get(key):
                    data[key] = value

            # Seed-search provenance (origin for local-SEO ranking).
            data['search_term'] = self.search_term
            data['search_location'] = self.location

            return data

        except Exception as e:
            print(f"Error extracting details: {str(e)}")
            return None

    # ------------------------------------------------------------------ output

    def coverage(self):
        """Per-column fill rate for the current run — a scrape-health check."""
        total = len(self.businesses)
        if not total:
            return {}
        columns = ("name", "phone", "website", "address", "category",
                   "rating", "reviews_count", "hours")
        return {
            col: sum(1 for b in self.businesses if str(b.get(col, "")).strip())
            for col in columns
        }

    def print_coverage(self):
        """Print how many of each field the run actually captured."""
        counts = self.coverage()
        if not counts:
            return
        total = len(self.businesses)
        print(f"\nField coverage across {total} businesses:")
        for col, hit in counts.items():
            pct = 100 * hit / total
            flag = "" if pct >= 80 else "   ← low"
            print(f"  {col:<14} {hit:>4}/{total}  ({pct:5.1f}%){flag}")

    def save_to_crm(self, progress=None):
        """Record this run in the CRM database as well as the CSV.

        The CSV stays the portable artefact; the database is what accumulates.
        A failure here must never lose a scrape, so it is reported and swallowed
        — the CSV has already been written by the time this runs.
        """
        if not self.businesses:
            return None
        try:
            from crm import Database
        except Exception as exc:  # pragma: no cover - optional dependency path
            print(f"CRM unavailable, CSV only: {exc}")
            return None

        try:
            with Database.open() as db:
                search_id = db.start_search(self.search_term, self.location)
                for position, business in enumerate(self.businesses, 1):
                    db.upsert_business(business, search_id=search_id,
                                       position=position)
                db.finish_search(search_id, len(self.businesses))
                stats = db.stats()
            message = (f"✓ Recorded {len(self.businesses)} business(es) in the CRM "
                       f"({stats['businesses']:,} total on file)")
            print(message)
            if progress:
                progress(message)
            return stats
        except Exception as exc:
            print(f"Could not write to the CRM: {exc}")
            return None

    def save_to_csv(self, filename=None):
        """Save scraped data to CSV file.

        With no explicit filename the rows land in
        data/<search term>/<location>/listings<date>-<time>.csv.
        """
        if not self.businesses:
            print("No data to save")
            return None

        if not filename:
            path = data_store.export_listings(
                self.businesses, self.search_term, self.location
            )
        else:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(
                    f, fieldnames=list(data_store.LISTING_FIELDS),
                    extrasaction='ignore', restval='',
                )
                writer.writeheader()
                writer.writerows(self.businesses)

        print(f"\n✓ Saved {len(self.businesses)} businesses to {path}")
        return path

    def save_to_json(self, filename=None):
        """Save scraped data to JSON file, alongside the CSV export"""
        if not self.businesses:
            print("No data to save")
            return None

        if filename:
            path = Path(filename)
        else:
            directory = data_store.search_dir(self.search_term, self.location)
            path = directory / data_store.timestamped_name("listings").replace(".csv", ".json")
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.businesses, f, indent=2, ensure_ascii=False)

        print(f"✓ Saved {len(self.businesses)} businesses to {path}")
        return path

    def close(self):
        """Close the browser"""
        self.driver.quit()


#: One business's card in the left-hand results feed.
_CARD_SELECTOR = 'div[role="feed"] div.Nv2PK'


def main():
    parser = argparse.ArgumentParser(description='Scrape Google Maps business listings')
    parser.add_argument('search_term', help='What to search for (e.g., "restaurants")')
    parser.add_argument('--location', default='', help='Location to search in (e.g., "New York, NY")')
    parser.add_argument('--output', default='csv', choices=['csv', 'json', 'both'], 
                       help='Output format')
    parser.add_argument('--filename', help='Custom output filename (without extension)')
    parser.add_argument('--headless', action='store_true', default=True,
                       help='Run browser in headless mode')
    parser.add_argument('--visible', action='store_true',
                       help='Run browser in visible mode (opposite of headless)')
    parser.add_argument('--max-scrolls', type=int, default=10,
                       help='Maximum number of scrolls to load results')
    
    args = parser.parse_args()
    
    # Handle headless vs visible mode
    headless = args.headless and not args.visible
    
    scraper = GoogleMapsScraper(headless=headless)
    
    try:
        scraper.search(args.search_term, args.location, max_scrolls=args.max_scrolls)
        scraper.scrape_listings()

        if args.output in ['csv', 'both']:
            csv_file = f"{args.filename}.csv" if args.filename else None
            scraper.save_to_csv(csv_file)
        
        if args.output in ['json', 'both']:
            json_file = f"{args.filename}.json" if args.filename else None
            scraper.save_to_json(json_file)

        scraper.save_to_crm()
        scraper.print_coverage()

    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        scraper.close()


def _check_licence() -> None:
    """Refuse to run unlicensed, with a message rather than a traceback.

    Running the module directly is a supported way to use this app, so it is
    gated exactly like the desktop screens are. The check hangs off the
    ``__main__`` guard rather than off ``main`` itself, because importing this
    module — which the tests, the TUI and the GUI all do — must never depend
    on a licence.
    """
    from licensing import console, plans

    console.require_or_exit(plans.SCRAPE_MAPS, action="Scraping Google Maps")


if __name__ == "__main__":
    _check_licence()
    main()
