#!/usr/bin/env python3
"""
School Athletics Contact Scraper
Reads school CSV results and scrapes athletics staff contact information from school websites.
Handles three common school website formats: tables, cards/divs, and text blocks.
"""

import csv
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse
import argparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from school_config import (
    SUPPORTED_SPORTS,
    ATHLETICS_PAGE_KEYWORDS,
    ATHLETICS_URL_PATTERNS,
    STAFF_TITLE_PATTERNS,
    GENERIC_EMAIL_PREFIXES,
    REQUEST_DELAY,
    PAGE_LOAD_TIMEOUT,
    MAX_PAGES_PER_SCHOOL,
)


class SchoolContactScraper:
    def __init__(self, headless=True, sports_filter=None, roles_filter=None):
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

        # Filters
        self.sports_filter = (
            [s.lower() for s in sports_filter] if sports_filter else None
        )
        self.roles_filter = roles_filter

        # Email regex
        self.email_pattern = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        )

        # Phone regex
        self.phone_pattern = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

    def load_schools_csv(self, filename):
        """Load schools from CSV file"""
        schools = []
        with open(filename, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                schools.append(row)
        return schools

    def process_schools(self, input_file):
        """Process all schools from CSV and extract athletics contacts"""
        schools = self.load_schools_csv(input_file)
        all_contacts = []

        print(f"\nProcessing {len(schools)} schools...")

        for idx, school in enumerate(schools):
            school_name = school.get("school_name", "Unknown")
            print(f"\n[{idx + 1}/{len(schools)}] {school_name}")

            try:
                contacts = self._scrape_school(school)
                all_contacts.extend(contacts)

                if contacts:
                    print(f"  Found {len(contacts)} contacts")
                    for contact in contacts:
                        email_str = f" - {contact['email']}" if contact.get("email") else ""
                        print(f"    {contact['contact_name']} ({contact['title']}){email_str}")
                else:
                    print("  No contacts found")

            except Exception as e:
                print(f"  Error: {str(e)[:100]}")

            time.sleep(REQUEST_DELAY)

        return all_contacts

    def _scrape_school(self, school_data):
        """Scrape a single school website for athletics contacts"""
        base_url = school_data.get("school_url", "")
        if not base_url:
            return []

        contacts = []

        # Step 1: Find athletics pages
        athletics_urls = self._find_athletics_pages(base_url)

        if not athletics_urls:
            print("  No athletics pages found, trying staff directory...")
            athletics_urls = self._find_staff_directory(base_url)

        if not athletics_urls:
            print("  No athletics or staff pages found")
            return []

        # Step 2: Extract contacts from each athletics page
        pages_crawled = 0
        for url in athletics_urls:
            if pages_crawled >= MAX_PAGES_PER_SCHOOL:
                break

            try:
                page_contacts = self._extract_contacts_from_page(url, school_data)
                contacts.extend(page_contacts)
                pages_crawled += 1
            except Exception as e:
                print(f"    Error on {url}: {str(e)[:80]}")

            time.sleep(1)

        # Deduplicate
        contacts = self._deduplicate_contacts(contacts)

        # Apply sports filter
        if self.sports_filter:
            contacts = [
                c
                for c in contacts
                if c.get("sport", "").lower() in self.sports_filter
                or c.get("sport", "").lower() == "unknown"
            ]

        return contacts

    def _find_athletics_pages(self, base_url):
        """Find athletics-related pages on a school website"""
        found_urls = []

        try:
            self.driver.get(base_url)
            time.sleep(2)
        except (TimeoutException, WebDriverException):
            return found_urls

        # Strategy 1: Scan navigation links
        try:
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                try:
                    href = link.get_attribute("href")
                    text = link.text.lower().strip()

                    if not href:
                        continue

                    for keyword in ATHLETICS_PAGE_KEYWORDS:
                        if keyword in text or keyword in href.lower():
                            if href not in found_urls and href.startswith("http"):
                                found_urls.append(href)
                            break
                except Exception:
                    continue
        except Exception:
            pass

        # Strategy 2: Try common URL patterns
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        for pattern in ATHLETICS_URL_PATTERNS:
            test_url = urljoin(base, pattern)
            if test_url not in found_urls:
                try:
                    self.driver.get(test_url)
                    time.sleep(1)
                    # Check if we landed on a real page (not 404)
                    if (
                        "404" not in self.driver.title.lower()
                        and "not found" not in self.driver.title.lower()
                        and self.driver.current_url.startswith(base)
                    ):
                        found_urls.append(self.driver.current_url)
                        break  # Found a working athletics page
                except (TimeoutException, WebDriverException):
                    continue

        return found_urls[:MAX_PAGES_PER_SCHOOL]

    def _find_staff_directory(self, base_url):
        """Find staff directory pages as fallback"""
        staff_keywords = ("staff", "directory", "faculty", "personnel", "team")
        found_urls = []

        try:
            self.driver.get(base_url)
            time.sleep(2)

            links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                try:
                    href = link.get_attribute("href")
                    text = link.text.lower().strip()

                    if not href:
                        continue

                    for keyword in staff_keywords:
                        if keyword in text or keyword in href.lower():
                            if href not in found_urls and href.startswith("http"):
                                found_urls.append(href)
                            break
                except Exception:
                    continue
        except Exception:
            pass

        return found_urls[:3]

    def _extract_contacts_from_page(self, url, school_data):
        """Extract athletics contacts from a single page"""
        try:
            self.driver.get(url)
            time.sleep(2)
        except (TimeoutException, WebDriverException):
            return []

        page_source = self.driver.page_source
        soup = BeautifulSoup(page_source, "lxml")

        contacts = []

        # Try all three extraction strategies
        contacts.extend(self._extract_contacts_from_staff_table(soup, school_data, url))
        contacts.extend(self._extract_contacts_from_staff_cards(soup, school_data, url))
        contacts.extend(self._extract_contacts_from_text_blocks(soup, school_data, url))

        # Extract page-level emails and match to contacts
        page_emails = self._extract_emails_from_page(soup, page_source)

        if page_emails and contacts:
            self._match_emails_to_contacts(contacts, page_emails)

        # If no structured contacts found but we have emails, create basic entries
        if not contacts and page_emails:
            sport = self._detect_sport_from_context(soup.get_text(), url)
            for email in page_emails[:5]:  # Limit to avoid noise
                contacts.append(
                    self._build_contact(
                        contact_name="",
                        title="Athletics Staff",
                        sport=sport,
                        email=email,
                        phone="",
                        school_data=school_data,
                    )
                )

        return contacts

    def _extract_contacts_from_staff_table(self, soup, school_data, url):
        """Extract contacts from HTML tables (most common on school sites)"""
        contacts = []

        tables = soup.find_all("table")
        for table in tables:
            headers = []
            header_row = table.find("tr")
            if header_row:
                headers = [
                    th.get_text(strip=True).lower()
                    for th in header_row.find_all(["th", "td"])
                ]

            # Check if this looks like a staff/coach table
            staff_headers = {"name", "coach", "sport", "email", "phone", "title", "position", "contact"}
            if not any(h in " ".join(headers) for h in staff_headers):
                continue

            # Map column indices
            col_map = {}
            for idx, header in enumerate(headers):
                if any(n in header for n in ("name", "coach", "staff")):
                    col_map["name"] = idx
                elif "sport" in header or "activity" in header:
                    col_map["sport"] = idx
                elif "title" in header or "position" in header or "role" in header:
                    col_map["title"] = idx
                elif "email" in header or "e-mail" in header:
                    col_map["email"] = idx
                elif "phone" in header or "tel" in header:
                    col_map["phone"] = idx

            # Parse data rows
            rows = table.find_all("tr")[1:]  # Skip header
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue

                cell_texts = [cell.get_text(strip=True) for cell in cells]

                name = cell_texts[col_map["name"]] if "name" in col_map and col_map["name"] < len(cell_texts) else ""
                sport = cell_texts[col_map["sport"]] if "sport" in col_map and col_map["sport"] < len(cell_texts) else ""
                title = cell_texts[col_map["title"]] if "title" in col_map and col_map["title"] < len(cell_texts) else ""
                email = cell_texts[col_map["email"]] if "email" in col_map and col_map["email"] < len(cell_texts) else ""
                phone = cell_texts[col_map["phone"]] if "phone" in col_map and col_map["phone"] < len(cell_texts) else ""

                # Also check for mailto links in cells
                if not email:
                    for cell in cells:
                        mailto = cell.find("a", href=re.compile(r"^mailto:"))
                        if mailto:
                            email = mailto["href"].replace("mailto:", "").split("?")[0]
                            break

                if not sport:
                    sport = self._detect_sport_from_context(
                        " ".join(cell_texts), url
                    )

                if not title:
                    name, title = self._parse_name_and_title(name)

                if name or email:
                    contacts.append(
                        self._build_contact(name, title, sport, email, phone, school_data)
                    )

        return contacts

    def _extract_contacts_from_staff_cards(self, soup, school_data, url):
        """Extract contacts from div/card-based staff listings"""
        contacts = []

        # Common CSS class patterns for staff cards
        card_selectors = [
            "div.staff-card",
            "div.coach-card",
            "div.directory-item",
            "div.staff-member",
            "div.coach",
            "article.staff",
            "div.person",
            "li.staff-item",
            "div.team-member",
            "div.fsElement",  # Finalsite CMS
        ]

        cards = []
        for selector in card_selectors:
            cards = soup.select(selector)
            if cards:
                break

        if not cards:
            return contacts

        for card in cards:
            text = card.get_text(separator=" ", strip=True)

            # Extract name (usually in heading or strong tag)
            name = ""
            name_el = card.find(["h2", "h3", "h4", "strong", "b"])
            if name_el:
                name = name_el.get_text(strip=True)

            # Extract title
            title = ""
            title_el = card.find(class_=re.compile(r"title|role|position", re.I))
            if title_el:
                title = title_el.get_text(strip=True)

            # Extract email from mailto link
            email = ""
            mailto = card.find("a", href=re.compile(r"^mailto:"))
            if mailto:
                email = mailto["href"].replace("mailto:", "").split("?")[0]
            else:
                # Try regex on card text
                emails = self.email_pattern.findall(card.decode_contents())
                if emails:
                    email = emails[0]

            # Extract phone
            phone = ""
            phone_match = self.phone_pattern.search(text)
            if phone_match:
                phone = phone_match.group()

            # Detect sport
            sport = self._detect_sport_from_context(text, url)

            if not title:
                name, title = self._parse_name_and_title(name + " " + text)

            if name or email:
                contacts.append(
                    self._build_contact(name, title, sport, email, phone, school_data)
                )

        return contacts

    def _extract_contacts_from_text_blocks(self, soup, school_data, url):
        """Extract contacts from unstructured text blocks"""
        contacts = []

        # Get visible text
        body = soup.find("body")
        if not body:
            return contacts

        text = body.get_text(separator="\n")
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        current_sport = self._detect_sport_from_context(text, url)

        for i, line in enumerate(lines):
            # Check if line matches a title pattern
            for role_key, pattern in STAFF_TITLE_PATTERNS.items():
                match = re.search(pattern, line)
                if match:
                    # Try to extract name from same line or adjacent
                    name, title = self._parse_name_and_title(line)

                    # Look for email in nearby lines
                    email = ""
                    phone = ""
                    context_window = " ".join(lines[max(0, i - 1) : min(len(lines), i + 3)])

                    email_matches = self.email_pattern.findall(context_window)
                    if email_matches:
                        email = email_matches[0]

                    phone_match = self.phone_pattern.search(context_window)
                    if phone_match:
                        phone = phone_match.group()

                    # Check if a sport name appears as a heading above
                    for j in range(max(0, i - 5), i):
                        detected = self._detect_sport_from_text(lines[j])
                        if detected != "Unknown":
                            current_sport = detected
                            break

                    if name or email:
                        contacts.append(
                            self._build_contact(
                                name, title, current_sport, email, phone, school_data
                            )
                        )
                    break

        return contacts

    def _build_contact(self, contact_name, title, sport, email, phone, school_data):
        """Build a standardized contact dictionary"""
        return {
            "contact_name": contact_name.strip() if contact_name else "",
            "title": title.strip() if title else "",
            "sport": sport.strip() if sport else "Unknown",
            "email": email.strip().lower() if email else "",
            "phone": phone.strip() if phone else "",
            "school_name": school_data.get("school_name", ""),
            "school_url": school_data.get("school_url", ""),
            "district": school_data.get("district", ""),
            "city": school_data.get("city", ""),
            "state": school_data.get("state", ""),
        }

    def _parse_name_and_title(self, text):
        """Parse a name and title from text like 'Coach Smith' or 'John Smith, Head Coach'"""
        if not text:
            return "", ""

        text = text.strip()

        # Pattern: "Name, Title" (comma separated) - check first for clean parsing
        if "," in text:
            parts = text.split(",", 1)
            potential_name = parts[0].strip()
            potential_title = parts[1].strip()

            # Check if the part after comma looks like a title
            for role_key, pattern in STAFF_TITLE_PATTERNS.items():
                if re.search(pattern, potential_title, re.IGNORECASE):
                    if len(potential_name) < 40:
                        return potential_name, potential_title

        # Pattern: "Title: Name" or "Title - Name"
        for role_key, pattern in STAFF_TITLE_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                title = match.group().strip()
                # Get text after the title match (the name part)
                after_title = text[match.end():].strip()
                before_title = text[:match.start()].strip()

                # Clean separators from the name part
                name = after_title if after_title else before_title
                name = re.sub(r"^[:\-,.\s]+", "", name).strip()
                name = re.sub(r"[:\-,.\s]+$", "", name).strip()
                name = re.sub(r"\s+", " ", name).strip()

                # If name was before the title, use that instead
                if not name and before_title:
                    name = re.sub(r"[:\-,.\s]+$", "", before_title).strip()

                # Filter out noise
                if len(name) > 50 or len(name) < 2:
                    name = ""

                return name, title

        return text if len(text) < 40 else "", ""

    def _detect_sport_from_context(self, text, url):
        """Detect which sport from URL path, headings, and surrounding text"""
        # Check URL path first
        url_sport = self._detect_sport_from_url(url)
        if url_sport != "Unknown":
            return url_sport

        # Check text content
        return self._detect_sport_from_text(text)

    def _detect_sport_from_url(self, url):
        """Detect sport from URL path segments"""
        if not url:
            return "Unknown"

        url_lower = url.lower()
        for sport in SUPPORTED_SPORTS:
            # Check for sport name in URL path
            sport_slug = sport.replace(" ", "-")
            sport_slug_alt = sport.replace(" ", "_")
            if (
                f"/{sport_slug}" in url_lower
                or f"/{sport_slug_alt}" in url_lower
                or f"/{sport.replace(' ', '')}" in url_lower
            ):
                return sport.title()

        return "Unknown"

    def _detect_sport_from_text(self, text):
        """Detect sport name from text content"""
        if not text:
            return "Unknown"

        text_lower = text.lower()
        for sport in SUPPORTED_SPORTS:
            if sport in text_lower:
                return sport.title()

        return "Unknown"

    def _extract_emails_from_page(self, soup, page_source):
        """Extract email addresses from a page, filtering out generic ones"""
        emails = set()

        # Strategy 1: mailto links (most reliable)
        for mailto in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
            email = mailto["href"].replace("mailto:", "").split("?")[0].strip().lower()
            if self._is_personal_email(email):
                emails.add(email)

        # Strategy 2: Regex on page source
        found = self.email_pattern.findall(page_source)
        for email in found:
            email = email.lower()
            if self._is_personal_email(email):
                emails.add(email)

        return list(emails)

    def _is_personal_email(self, email):
        """Check if an email appears to be a personal (not generic) address"""
        if not email or "@" not in email:
            return False

        email_lower = email.lower()

        # Filter out generic prefixes
        for prefix in GENERIC_EMAIL_PREFIXES:
            if email_lower.startswith(prefix):
                return False

        # Filter out common false positives
        false_positives = ("example.com", "placeholder", "yoursite", "yourdomain", "sentry", "wixpress")
        for fp in false_positives:
            if fp in email_lower:
                return False

        # Filter out image-like emails
        if re.search(r"\.(jpg|png|gif|jpeg|svg|webp)$", email_lower):
            return False

        return True

    def _match_emails_to_contacts(self, contacts, page_emails):
        """Try to match unmatched emails to contacts without emails"""
        unmatched_emails = list(page_emails)

        # Remove already-assigned emails
        for contact in contacts:
            if contact.get("email") and contact["email"] in unmatched_emails:
                unmatched_emails.remove(contact["email"])

        # Assign remaining emails to contacts without them
        email_idx = 0
        for contact in contacts:
            if not contact.get("email") and email_idx < len(unmatched_emails):
                # Try to match by name similarity to email
                name_parts = contact.get("contact_name", "").lower().split()
                best_match = None

                for email in unmatched_emails:
                    local_part = email.split("@")[0].lower()
                    if any(part in local_part for part in name_parts if len(part) > 2):
                        best_match = email
                        break

                if best_match:
                    contact["email"] = best_match
                    unmatched_emails.remove(best_match)
                else:
                    contact["email"] = unmatched_emails[email_idx]
                    email_idx += 1

    def _deduplicate_contacts(self, contacts):
        """Remove duplicate contacts based on email or name+school combo"""
        seen = set()
        unique = []

        for contact in contacts:
            # Dedup key: email if available, otherwise name+school
            if contact.get("email"):
                key = contact["email"].lower()
            elif contact.get("contact_name"):
                key = f"{contact['contact_name'].lower()}_{contact.get('school_name', '').lower()}"
            else:
                continue  # Skip contacts with neither email nor name

            if key not in seen:
                seen.add(key)
                unique.append(contact)

        return unique

    def save_to_csv(self, results, filename=None):
        """Save results to CSV file"""
        if not filename:
            filename = f"school_contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        if not results:
            print("No results to save")
            return filename

        keys = [
            "contact_name",
            "title",
            "sport",
            "email",
            "phone",
            "school_name",
            "school_url",
            "district",
            "city",
            "state",
        ]

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(results)

        # Stats
        with_email = sum(1 for r in results if r.get("email"))
        with_phone = sum(1 for r in results if r.get("phone"))
        sports = set(r.get("sport", "Unknown") for r in results)

        print(f"\n{'=' * 60}")
        print(f"Saved {len(results)} contacts to {filename}")
        print(f"  - {with_email} with email addresses")
        print(f"  - {with_phone} with phone numbers")
        print(f"  - Sports found: {', '.join(sorted(sports))}")
        print(f"{'=' * 60}")

        return filename

    def save_to_json(self, results, filename=None):
        """Save results to JSON file"""
        if not filename:
            filename = f"school_contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        if not results:
            print("No results to save")
            return filename

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"Saved to {filename}")
        return filename

    def close(self):
        """Close the browser"""
        self.driver.quit()


def main():
    parser = argparse.ArgumentParser(
        description="Scrape athletics staff contacts from school websites"
    )
    parser.add_argument("csv_file", help="Input CSV file from school sports scraper")
    parser.add_argument(
        "--sports",
        default=None,
        help='Comma-separated sports to filter (e.g., "football,basketball")',
    )
    parser.add_argument(
        "--roles",
        default=None,
        help='Comma-separated roles to filter (e.g., "athletic_director,head_coach")',
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES_PER_SCHOOL,
        help="Maximum athletics pages to crawl per school",
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

    sports_filter = args.sports.split(",") if args.sports else None
    roles_filter = args.roles.split(",") if args.roles else None

    scraper = SchoolContactScraper(
        headless=headless,
        sports_filter=sports_filter,
        roles_filter=roles_filter,
    )

    try:
        results = scraper.process_schools(args.csv_file)

        if args.output in ["csv", "both"]:
            csv_file = f"{args.filename}.csv" if args.filename else None
            scraper.save_to_csv(results, csv_file)

        if args.output in ["json", "both"]:
            json_file = f"{args.filename}.json" if args.filename else None
            scraper.save_to_json(results, json_file)

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

    console.require_or_exit(plans.SCHOOL_PIPELINE, action="The K-12 fundraiser pipeline")


if __name__ == "__main__":
    _check_licence()
    main()
