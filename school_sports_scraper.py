#!/usr/bin/env python3
"""
School Sports Scraper
Searches for K-12 schools by geographic area using a multi-layer approach:
  1. Direct k12 domain construction (instant, no network required)
  2. DuckDuckGo HTML search (no API key, no bot detection)
  3. Bing HTML search (fallback)
  4. Selenium Google search (last resort)
"""

import time
import csv
import json
import re
import random
import urllib.parse
from datetime import datetime
from urllib.parse import urlparse
import requests
import argparse

from school_config import (
    SCHOOL_DOMAIN_PATTERNS,
    SCHOOL_TITLE_KEYWORDS,
    EXCLUDED_DOMAINS,
    STATE_ABBREVIATIONS,
    REQUEST_DELAY,
    PAGE_LOAD_TIMEOUT,
    MAX_QUERIES_PER_TARGET,
)

# ---------------------------------------------------------------------------
# Search query templates (expanded)
# ---------------------------------------------------------------------------
QUERIES = [
    "{city} {state} high school athletics site:*.k12.{state_abbrev}.us OR site:*.edu OR site:*schools.org",
    "{city} {state} high school athletics",
    "{city} {state} school district athletic director email",
    "{city} {state} high school sports coaches directory",
    "site:*.k12.{state_abbrev}.us {city} athletics coaches",
    "{city} City Schools athletics",
    "{city} Local Schools athletics coaches",
    "{city} {state} high school football basketball baseball coaches",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_abbrev(state: str) -> str:
    if len(state) == 2:
        return state.lower()
    return STATE_ABBREVIATIONS.get(state.title(), state[:2].lower())


_EXTRA_SCHOOL_PATTERNS = (
    "schools.org",
    "schools.net",
    "schools.us",
    "schooldistrict.",
    "cityschools.",
    "localschools.",
    "ccsoh.us",          # Columbus City Schools
    "wcsd.",             # Generic western county school district
    "hcsd.",
    "mcsd.",
    "cusd.",
)

def _is_school_url(url: str, title: str = "", snippet: str = "") -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    for exc in EXCLUDED_DOMAINS:
        if exc in domain:
            return False
    for pat in SCHOOL_DOMAIN_PATTERNS:
        if pat in domain:
            return True
    for pat in _EXTRA_SCHOOL_PATTERNS:
        if pat in domain:
            return True
    combined = f"{title} {snippet}".lower()
    # Title/snippet must mention school AND athletics/coaches to qualify
    has_school = any(kw in combined for kw in SCHOOL_TITLE_KEYWORDS)
    has_sports = any(kw in combined for kw in ("athletics", "coach", "sports", "athletic director", "varsity"))
    if has_school and has_sports:
        return True
    return False


def _decode_ddg_url(encoded: str) -> str:
    """Decode DuckDuckGo redirect URLs like //duckduckgo.com/l/?uddg=https%3A%2F%2F..."""
    if "uddg=" in encoded:
        try:
            raw = encoded.split("uddg=")[1].split("&")[0]
            return urllib.parse.unquote(raw)
        except Exception:
            pass
    if encoded.startswith("//"):
        encoded = "https:" + encoded
    return encoded


def _extract_district_from_domain(domain: str) -> str:
    if ".k12." in domain:
        parts = domain.replace("www.", "").split(".")
        if parts:
            return parts[0].replace("-", " ").title()
    return ""


def _clean_school_name(raw: str) -> str:
    for suffix in [
        " - Home", " | Home", " - Official", " | Official",
        " - Homepage", " | Homepage", " - Athletics", " | Athletics",
        " Athletics", " - Sports", " | Sports",
    ]:
        raw = raw.replace(suffix, "")
    return raw.strip()


# ---------------------------------------------------------------------------
# Layer 1: Direct k12 domain construction
# ---------------------------------------------------------------------------

def probe_k12_domains(city: str, state_abbrev: str) -> list[dict]:
    """
    Construct likely k12 domain names and probe them with a HEAD request.
    Ohio schools follow: <districtname>.k12.oh.us
    """
    city_slug = city.lower().replace(" ", "").replace("-", "")
    city_slug_dash = city.lower().replace(" ", "-")

    candidates = [
        f"www.{city_slug}.k12.{state_abbrev}.us",
        f"{city_slug}.k12.{state_abbrev}.us",
        f"www.{city_slug_dash}.k12.{state_abbrev}.us",
        f"{city_slug_dash}.k12.{state_abbrev}.us",
        # Some districts use the city name + "schools"
        f"www.{city_slug}schools.org",
        f"www.{city_slug}local.org",
        f"www.{city_slug}city.k12.{state_abbrev}.us",
    ]

    found = []
    session = requests.Session()
    session.headers.update(HEADERS)

    for candidate in candidates:
        url = f"https://{candidate}"
        try:
            resp = session.head(url, timeout=5, allow_redirects=True)
            if resp.status_code < 400:
                final_url = resp.url
                domain = urlparse(final_url).netloc
                found.append({
                    "url": final_url,
                    "title": f"{city} Schools",
                    "snippet": f"Direct domain probe: {candidate}",
                    "domain": domain,
                    "source": "direct_probe",
                })
                print(f"  ✓ Direct probe hit: {final_url}")
        except Exception:
            pass

    return found


# ---------------------------------------------------------------------------
# Layer 2: DuckDuckGo HTML search (no API, no Selenium)
# ---------------------------------------------------------------------------

def search_ddg(query: str) -> list[dict]:
    """Search DuckDuckGo HTML endpoint. Returns list of {url, title, snippet}."""
    try:
        params = {"q": query, "kl": "us-en"}
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params=params,
            headers=HEADERS,
            timeout=12,
        )
        if resp.status_code != 200:
            return []

        html = resp.text

        # Extract DDG result URLs (they are encoded redirect links)
        raw_urls = re.findall(r'class="result__a"[^>]*href="([^"]+)"', html)
        titles = re.findall(r'class="result__a"[^>]*href="[^"]*">([^<]+)<', html)
        snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)<', html)

        results = []
        for i, raw in enumerate(raw_urls):
            url = _decode_ddg_url(raw)
            title = titles[i] if i < len(titles) else ""
            snippet = snippets[i] if i < len(snippets) else ""
            if _is_school_url(url, title, snippet):
                results.append({"url": url, "title": title, "snippet": snippet, "source": "ddg"})

        return results

    except Exception as e:
        print(f"    DDG error: {str(e)[:80]}")
        return []


# ---------------------------------------------------------------------------
# Layer 3: Bing HTML search
# ---------------------------------------------------------------------------

def search_bing(query: str) -> list[dict]:
    """Search Bing HTML. Returns list of {url, title, snippet}."""
    try:
        params = {"q": query, "count": "20"}
        resp = requests.get(
            "https://www.bing.com/search",
            params=params,
            headers=HEADERS,
            timeout=12,
        )
        if resp.status_code != 200:
            return []

        html = resp.text

        # Bing result links
        urls = re.findall(r'<a href="(https?://[^"]+)"[^>]*class="tilk"', html)
        if not urls:
            # fallback pattern
            urls = re.findall(r'<h2[^>]*><a href="(https?://[^"]+)"', html)

        titles_raw = re.findall(r'<h2[^>]*><a[^>]+>([^<]+)</a>', html)
        snippets_raw = re.findall(r'class="b_caption"[^>]*>.*?<p[^>]*>([^<]+)</p>', html, re.DOTALL)

        results = []
        for i, url in enumerate(urls):
            title = titles_raw[i] if i < len(titles_raw) else ""
            snippet = snippets_raw[i] if i < len(snippets_raw) else ""
            if _is_school_url(url, title, snippet):
                results.append({"url": url, "title": title, "snippet": snippet, "source": "bing"})

        return results

    except Exception as e:
        print(f"    Bing error: {str(e)[:80]}")
        return []


# ---------------------------------------------------------------------------
# Layer 4: Selenium Google (last resort)
# ---------------------------------------------------------------------------

def search_google_selenium(query: str, headless: bool = True) -> list[dict]:
    """Selenium Google search. Used only when all other layers find nothing."""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import NoSuchElementException

        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

        try:
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num=20"
            driver.get(url)
            time.sleep(random.uniform(2, 4))

            results = []
            for result in driver.find_elements(By.CSS_SELECTOR, "div.g"):
                try:
                    link = result.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                    try:
                        title = result.find_element(By.CSS_SELECTOR, "h3").text
                    except NoSuchElementException:
                        title = ""
                    try:
                        snippet = result.find_element(By.CSS_SELECTOR, "div.VwiC3b, span.aCOpRe").text
                    except NoSuchElementException:
                        snippet = ""
                    if link and _is_school_url(link, title, snippet):
                        results.append({"url": link, "title": title, "snippet": snippet, "source": "google"})
                except Exception:
                    continue
            return results
        finally:
            driver.quit()

    except Exception as e:
        print(f"    Selenium error: {str(e)[:80]}")
        return []


# ---------------------------------------------------------------------------
# Metadata fetch (lightweight, no Selenium)
# ---------------------------------------------------------------------------

def fetch_school_metadata(url: str, fallback_title: str, city: str, state: str) -> dict | None:
    """Fetch page title and basic metadata from a school URL via requests."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        final_url = resp.url
        parsed = urlparse(final_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Extract title from HTML
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", resp.text, re.IGNORECASE)
        page_title = _clean_school_name(title_match.group(1)) if title_match else fallback_title

        # Extract h1 as backup
        if not page_title or page_title in ("", "Unknown"):
            h1_match = re.search(r"<h1[^>]*>([^<]+)</h1>", resp.text, re.IGNORECASE)
            if h1_match:
                page_title = _clean_school_name(h1_match.group(1))

        district = _extract_district_from_domain(parsed.netloc)

        # Detect school type
        combined = (page_title + " " + resp.text[:2000]).lower()
        if "middle school" in combined or "junior high" in combined:
            school_type = "middle school"
        elif "elementary" in combined:
            school_type = "elementary school"
        else:
            school_type = "high school"

        return {
            "school_name": page_title or fallback_title,
            "school_url": base_url,
            "full_url": final_url,
            "district": district,
            "city": city,
            "state": state,
            "school_type": school_type,
            "scraped_at": datetime.now().isoformat(),
        }

    except Exception as e:
        # Use fallback metadata from search result
        parsed = urlparse(url)
        return {
            "school_name": _clean_school_name(fallback_title) or f"{city} School",
            "school_url": f"{parsed.scheme}://{parsed.netloc}",
            "full_url": url,
            "district": _extract_district_from_domain(parsed.netloc),
            "city": city,
            "state": state,
            "school_type": "high school",
            "scraped_at": datetime.now().isoformat(),
        }


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------

class SchoolSportsScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.schools: list[dict] = []

    def search_schools(
        self,
        city: str,
        state: str,
        school_type: str = "high school",
        district: str | None = None,
        max_results: int = 50,
    ) -> list[dict]:

        state_ab = _state_abbrev(state)
        raw_results: list[dict] = []

        # --- Layer 1: direct k12 probe ---
        print("\n[Layer 1] Probing known k12 domain patterns...")
        probe_hits = probe_k12_domains(city, state_ab)
        raw_results.extend(probe_hits)

        # --- Layer 2: DDG HTML queries ---
        queries = self._build_queries(city, state, state_ab, district, school_type)
        total = min(len(queries), MAX_QUERIES_PER_TARGET)
        print(f"\n[Layer 2] DuckDuckGo HTML search ({total} queries)...")

        for idx, q in enumerate(queries[:total]):
            print(f"  [{idx+1}/{total}] {q}")
            hits = search_ddg(q)
            print(f"    → {len(hits)} school result(s)")
            raw_results.extend(hits)
            if len(raw_results) >= max_results:
                break
            time.sleep(REQUEST_DELAY + random.uniform(0.5, 1.5))

        # --- Layer 3: Bing if still sparse ---
        if len(raw_results) < 3:
            print(f"\n[Layer 3] Bing HTML search (got {len(raw_results)} so far)...")
            bing_q = f"{city} {state} high school athletics site:*.k12.{state_ab}.us OR site:*.edu"
            hits = search_bing(bing_q)
            print(f"    → {len(hits)} result(s)")
            raw_results.extend(hits)

            if not hits:
                bing_q2 = f"{city} {state} high school football basketball coaches"
                hits2 = search_bing(bing_q2)
                print(f"    → {len(hits2)} result(s) (second query)")
                raw_results.extend(hits2)

        # --- Layer 4: Selenium Google last resort ---
        if len(raw_results) < 2:
            print(f"\n[Layer 4] Selenium Google fallback...")
            g_q = f"{city} {state} high school athletics"
            hits = search_google_selenium(g_q, headless=self.headless)
            print(f"    → {len(hits)} result(s)")
            raw_results.extend(hits)

        # Deduplicate by domain
        unique = self._deduplicate(raw_results)
        print(f"\nFound {len(unique)} unique school(s) — fetching metadata...")

        for idx, r in enumerate(unique[:max_results]):
            url = r["url"]
            title = r.get("title", "")
            print(f"  [{idx+1}/{min(len(unique), max_results)}] {url}")
            meta = fetch_school_metadata(url, title, city, state)
            if meta:
                self.schools.append(meta)
            time.sleep(REQUEST_DELAY)

        return self.schools

    # ------------------------------------------------------------------

    def _build_queries(
        self,
        city: str,
        state: str,
        state_ab: str,
        district: str | None,
        school_type: str,
    ) -> list[str]:
        q_list = []
        if district:
            q_list.append(f"{district} school district athletics {state}")
            q_list.append(f"{district} athletic director email")

        for tmpl in QUERIES:
            q = (
                tmpl
                .replace("{city}", city)
                .replace("{state}", state)
                .replace("{state_abbrev}", state_ab)
            )
            q_list.append(q)

        if school_type in ("middle school", "all"):
            q_list.append(f"{city} {state} middle school athletics coaches")

        return q_list

    def _deduplicate(self, results: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for r in results:
            parsed = urlparse(r.get("url", ""))
            domain = parsed.netloc.lower().replace("www.", "")
            if domain and domain not in seen:
                seen.add(domain)
                unique.append(r)
        return unique

    def save_to_csv(self, filename: str | None = None) -> str:
        if not filename:
            filename = f"school_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        if not self.schools:
            print("No school data to save")
            return filename
        keys = [
            "school_name", "school_url", "full_url", "district",
            "city", "state", "school_type", "scraped_at",
        ]
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.schools)
        print(f"\nSaved {len(self.schools)} school(s) to {filename}")
        return filename

    def save_to_json(self, filename: str | None = None) -> str:
        if not filename:
            filename = f"school_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        if not self.schools:
            print("No school data to save")
            return filename
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.schools, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(self.schools)} school(s) to {filename}")
        return filename

    def close(self):
        pass  # No persistent browser to close


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Find K-12 schools in a city/state using multi-layer search"
    )
    parser.add_argument("--city", required=True, help='City name (e.g., "Zanesville")')
    parser.add_argument("--state", required=True, help='State name or abbreviation (e.g., "OH")')
    parser.add_argument("--district", default=None, help="School district name (optional)")
    parser.add_argument(
        "--school-type",
        default="high school",
        choices=["high school", "middle school", "all"],
    )
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--output", default="csv", choices=["csv", "json", "both"])
    parser.add_argument("--filename", help="Custom output filename (no extension)")
    parser.add_argument("--visible", action="store_true", help="Visible browser (for Selenium fallback)")

    args = parser.parse_args()

    scraper = SchoolSportsScraper(headless=not args.visible)

    try:
        scraper.search_schools(
            city=args.city,
            state=args.state,
            school_type=args.school_type,
            district=args.district,
            max_results=args.max_results,
        )

        if args.output in ("csv", "both"):
            scraper.save_to_csv(f"{args.filename}.csv" if args.filename else None)
        if args.output in ("json", "both"):
            scraper.save_to_json(f"{args.filename}.json" if args.filename else None)

    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
        if scraper.schools:
            scraper.save_to_csv()
    except Exception as e:
        print(f"Error: {e}")
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

    console.require_or_exit(plans.SCHOOL_PIPELINE, action="The K-12 fundraiser pipeline")


if __name__ == "__main__":
    _check_licence()
    main()
