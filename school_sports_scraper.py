#!/usr/bin/env python3
"""
School Sports Scraper
Searches Google for K-12 schools by geographic area and collects school metadata.
"""

import time
import csv
import json
import random
from datetime import datetime
from urllib.parse import urlparse, urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
import argparse

from school_config import (
    SEARCH_QUERY_TEMPLATES,
    SCHOOL_DOMAIN_PATTERNS,
    SCHOOL_TITLE_KEYWORDS,
    EXCLUDED_DOMAINS,
    STATE_ABBREVIATIONS,
    REQUEST_DELAY,
    PAGE_LOAD_TIMEOUT,
    MAX_QUERIES_PER_TARGET,
)


class SchoolSportsScraper:
    def __init__(self, headless=True):
        """Initialize the scraper with Chrome options"""
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        self.wait = WebDriverWait(self.driver, 10)
        self.schools = []

    def search_schools(self, city, state, school_type="high school", district=None, max_results=50):
        """
        Search Google for schools in a geographic area.

        Args:
            city: City name
            state: State name or abbreviation
            school_type: "high school", "middle school", or "all"
            district: Optional school district name
            max_results: Maximum number of schools to collect
        """
        queries = self._build_search_queries(city, state, school_type, district)
        all_results = []

        for idx, query in enumerate(queries[:MAX_QUERIES_PER_TARGET]):
            print(f"\n[Query {idx + 1}/{min(len(queries), MAX_QUERIES_PER_TARGET)}] {query}")

            try:
                results = self._search_google(query)
                all_results.extend(results)
                print(f"  Found {len(results)} potential school results")
            except Exception as e:
                print(f"  Search error: {str(e)[:100]}")

            # Respectful delay between searches
            delay = REQUEST_DELAY + random.uniform(0, 2)
            time.sleep(delay)

            if len(all_results) >= max_results:
                break

        # Deduplicate and filter
        unique_schools = self._deduplicate_schools(all_results)
        print(f"\nFound {len(unique_schools)} unique schools after deduplication")

        # Extract metadata for each school
        for idx, school in enumerate(unique_schools[:max_results]):
            print(f"\n[{idx + 1}/{min(len(unique_schools), max_results)}] Extracting metadata: {school.get('title', 'Unknown')}")

            try:
                metadata = self._extract_school_metadata(school)
                if metadata:
                    metadata["city"] = city
                    metadata["state"] = state
                    metadata["scraped_at"] = datetime.now().isoformat()
                    self.schools.append(metadata)
                    print(f"  Found: {metadata['school_name']}")
            except Exception as e:
                print(f"  Error: {str(e)[:100]}")

            time.sleep(REQUEST_DELAY)

        return self.schools

    def _build_search_queries(self, city, state, school_type, district=None):
        """Build Google search queries for the given geography"""
        # Resolve state abbreviation
        state_abbrev = state.lower()
        if len(state) > 2:
            state_abbrev = STATE_ABBREVIATIONS.get(state, state.lower()[:2])

        queries = []

        if district:
            queries.append(
                SEARCH_QUERY_TEMPLATES["by_district"].format(
                    district=district, state=state
                )
            )

        if school_type in ("high school", "all"):
            queries.append(
                SEARCH_QUERY_TEMPLATES["by_city"].format(city=city, state=state)
            )
            queries.append(
                SEARCH_QUERY_TEMPLATES["by_city_coaches"].format(
                    city=city, state=state
                )
            )
            queries.append(
                SEARCH_QUERY_TEMPLATES["by_k12_domain"].format(
                    city=city, state_abbrev=state_abbrev
                )
            )

        if school_type in ("middle school", "all"):
            queries.append(
                SEARCH_QUERY_TEMPLATES["by_city_middle"].format(
                    city=city, state=state
                )
            )

        return queries

    def _search_google(self, query):
        """Execute a Google search and extract results"""
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=20"
        self.driver.get(url)
        time.sleep(2)

        results = []

        try:
            # Find search result containers
            search_results = self.driver.find_elements(By.CSS_SELECTOR, "div.g")

            for result in search_results:
                try:
                    # Extract link
                    link_el = result.find_element(By.CSS_SELECTOR, "a")
                    href = link_el.get_attribute("href")

                    # Extract title
                    try:
                        title = result.find_element(By.CSS_SELECTOR, "h3").text
                    except NoSuchElementException:
                        title = ""

                    # Extract snippet
                    try:
                        snippet_el = result.find_element(
                            By.CSS_SELECTOR, "div.VwiC3b, span.aCOpRe"
                        )
                        snippet = snippet_el.text
                    except NoSuchElementException:
                        snippet = ""

                    if href and self._is_school_website(href, title, snippet):
                        results.append(
                            {"url": href, "title": title, "snippet": snippet}
                        )

                except (NoSuchElementException, Exception):
                    continue

        except Exception as e:
            print(f"  Error parsing search results: {str(e)[:100]}")

        return results

    def _is_school_website(self, url, title="", snippet=""):
        """Determine if a URL belongs to a school website"""
        if not url:
            return False

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Exclude known non-school domains
        for excluded in EXCLUDED_DOMAINS:
            if excluded in domain:
                return False

        # Check for school domain patterns
        for pattern in SCHOOL_DOMAIN_PATTERNS:
            if pattern in domain:
                return True

        # Check title and snippet for school keywords
        combined_text = f"{title} {snippet}".lower()
        for keyword in SCHOOL_TITLE_KEYWORDS:
            if keyword in combined_text:
                return True

        return False

    def _extract_school_metadata(self, search_result):
        """Visit a school website and extract metadata"""
        url = search_result.get("url", "")
        if not url:
            return None

        try:
            self.driver.get(url)
            time.sleep(2)
        except (TimeoutException, WebDriverException):
            # Use search result data as fallback
            pass

        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Extract school name
        school_name = self._extract_school_name(search_result)

        # Detect school type
        school_type = self._detect_school_type(school_name, search_result.get("snippet", ""))

        # Extract district from domain or content
        district = self._extract_district(parsed.netloc, school_name)

        return {
            "school_name": school_name,
            "school_url": base_url,
            "full_url": url,
            "district": district,
            "school_type": school_type,
        }

    def _extract_school_name(self, search_result):
        """Extract school name from page or search result"""
        # Try page title first
        try:
            page_title = self.driver.title
            if page_title:
                # Clean common suffixes
                for suffix in [
                    " - Home",
                    " | Home",
                    " - Official",
                    " | Official",
                    " - Homepage",
                ]:
                    page_title = page_title.replace(suffix, "")
                if len(page_title) < 100:
                    return page_title.strip()
        except Exception:
            pass

        # Try h1
        try:
            h1 = self.driver.find_element(By.TAG_NAME, "h1").text
            if h1 and len(h1) < 100:
                return h1.strip()
        except Exception:
            pass

        # Fall back to search result title
        title = search_result.get("title", "")
        if title:
            return title.strip()

        return "Unknown School"

    def _detect_school_type(self, name, snippet=""):
        """Detect whether this is a high school, middle school, etc."""
        combined = f"{name} {snippet}".lower()

        if "middle school" in combined or "junior high" in combined:
            return "middle school"
        if "elementary" in combined:
            return "elementary school"
        if "high school" in combined or "secondary" in combined:
            return "high school"
        if "k-8" in combined or "k8" in combined:
            return "K-8"

        return "high school"  # Default assumption

    def _extract_district(self, domain, school_name):
        """Extract school district name from domain or school name"""
        # Try to extract from .k12 domain
        # Pattern: district.k12.state.us
        if ".k12." in domain:
            parts = domain.split(".")
            if len(parts) >= 4:
                district_part = parts[0]
                if district_part != "www":
                    return district_part.replace("-", " ").title()

        # Look for district in school name
        lower_name = school_name.lower()
        for keyword in ("school district", "isd", "usd", "unified"):
            if keyword in lower_name:
                return school_name

        return ""

    def _deduplicate_schools(self, results):
        """Remove duplicate school entries based on URL domain"""
        seen_domains = set()
        unique = []

        for result in results:
            parsed = urlparse(result.get("url", ""))
            domain = parsed.netloc.lower()

            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                unique.append(result)

        return unique

    def save_to_csv(self, filename=None):
        """Save scraped school data to CSV file"""
        if not filename:
            filename = f"schools_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        if not self.schools:
            print("No school data to save")
            return filename

        keys = [
            "school_name",
            "school_url",
            "full_url",
            "district",
            "city",
            "state",
            "school_type",
            "scraped_at",
        ]

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.schools)

        print(f"\nSaved {len(self.schools)} schools to {filename}")
        return filename

    def save_to_json(self, filename=None):
        """Save scraped school data to JSON file"""
        if not filename:
            filename = f"schools_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        if not self.schools:
            print("No school data to save")
            return filename

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.schools, f, indent=2, ensure_ascii=False)

        print(f"Saved {len(self.schools)} schools to {filename}")
        return filename

    def close(self):
        """Close the browser"""
        self.driver.quit()


def main():
    parser = argparse.ArgumentParser(
        description="Search Google for K-12 schools by geographic area"
    )
    parser.add_argument(
        "--city", required=True, help='City name (e.g., "Columbus")'
    )
    parser.add_argument(
        "--state", required=True, help='State name or abbreviation (e.g., "Ohio" or "OH")'
    )
    parser.add_argument(
        "--district", default=None, help='School district name (optional)'
    )
    parser.add_argument(
        "--school-type",
        default="high school",
        choices=["high school", "middle school", "all"],
        help="Type of schools to search for",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum number of schools to collect",
    )
    parser.add_argument(
        "--output",
        default="csv",
        choices=["csv", "json", "both"],
        help="Output format",
    )
    parser.add_argument("--filename", help="Custom output filename (without extension)")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode (opposite of headless)",
    )

    args = parser.parse_args()
    headless = args.headless and not args.visible

    scraper = SchoolSportsScraper(headless=headless)

    try:
        scraper.search_schools(
            city=args.city,
            state=args.state,
            school_type=args.school_type,
            district=args.district,
            max_results=args.max_results,
        )

        if args.output in ["csv", "both"]:
            csv_file = f"{args.filename}.csv" if args.filename else None
            scraper.save_to_csv(csv_file)

        if args.output in ["json", "both"]:
            json_file = f"{args.filename}.json" if args.filename else None
            scraper.save_to_json(json_file)

    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
