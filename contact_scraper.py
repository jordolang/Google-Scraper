#!/usr/bin/env python3
"""
Website Contact Scraper
Reads Google Maps CSV results and scrapes contact information from business websites
"""

import os
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import argparse

import data_store
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


# Categories the desktop app's "Data Categories" panel reports on. Each entry
# is (key, label) in display order; ``page_insights`` returns a count per key.
INSIGHT_CATEGORIES = (
    ("business_info", "Business Info"),
    ("contact_info", "Contact Info"),
    ("services", "Services"),
    ("about_us", "About Us"),
    ("reviews", "Reviews/Testimonials"),
    ("social_links", "Social Media Links"),
    ("images", "Images"),
    ("team", "Team/Staff"),
    ("blog_news", "Blog/News"),
    ("certifications", "Certifications"),
    ("hours", "Hours of Operation"),
)

_SOCIAL_HOSTS = (
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "pinterest.com", "yelp.com",
)

_SECTION_WORDS = {
    "services": ("service", "what we do", "our work", "specialti"),
    "about_us": ("about us", "about our", "our story", "who we are"),
    "reviews": ("testimonial", "review", "what our customers", "rated us"),
    "team": ("our team", "meet the team", "staff", "technicians", "our crew"),
    "blog_news": ("blog", "news", "articles", "latest posts"),
    "certifications": ("certified", "licensed", "accredited", "bbb", "insured",
                       "certification", "award"),
    "hours": ("hours", "open today", "monday", "mon -", "mon-", "appointment only"),
}


def social_links(html):
    """Every distinct social-profile URL linked from a page."""
    found = []
    for match in re.finditer(r'href=["\']([^"\']+)["\']', html or "", re.I):
        url = match.group(1)
        host = urlparse(url).netloc.lower()
        if not host:
            continue
        for social in _SOCIAL_HOSTS:
            # "notfacebook.com" ends with "facebook.com" but is not it; only
            # the domain itself or a subdomain of it counts.
            if (host == social or host.endswith("." + social)) and url not in found:
                found.append(url)
                break
    return found


def page_insights(html="", text=""):
    """Count what a business website actually shows, by category.

    Deliberately forgiving: small-business sites are built every which way, so
    this counts evidence (a services heading, an <img>, a Facebook link) rather
    than trying to parse a structure that is rarely there. Returns a count per
    key in :data:`INSIGHT_CATEGORIES`; 0 means "nothing found".
    """
    html = html or ""
    text = text or ""
    haystack = (text + " " + html).lower()
    counts = {key: 0 for key, _label in INSIGHT_CATEGORIES}

    counts["business_info"] = 1 if (html or text) else 0
    counts["images"] = len(re.findall(r"<img\b", html, re.I))
    links = social_links(html)
    counts["social_links"] = len(links)

    # Service-ish list items and headings give a rough menu size.
    headings = re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", html, re.I | re.S)
    stripped = [re.sub(r"<[^>]+>", " ", h).strip().lower() for h in headings]
    for key, words in _SECTION_WORDS.items():
        hits = sum(1 for h in stripped if any(word in h for word in words))
        if not hits and any(word in haystack for word in words):
            hits = 1
        counts[key] = hits

    if counts["services"]:
        # A services section usually lists its offerings; count those so the UI
        # can say "8 services found" rather than just "yes". Only the section
        # itself is counted — counting every <li> on the page would score the
        # nav and the footer as services.
        listed = _service_items(html)
        if listed:
            counts["services"] = max(counts["services"], min(len(listed), 40))

    return counts


def _services_section(html):
    """The markup between a services heading and the next heading."""
    match = re.search(
        r"<h[1-4][^>]*>(?:(?!</h[1-4]>).)*?(?:service|what we do|our work)"
        r"(?:(?!</h[1-4]>).)*?</h[1-4]>",
        html, re.I | re.S,
    )
    if not match:
        return ""
    rest = html[match.end():]
    following = re.search(r"<h[1-4][^>]*>", rest, re.I)
    return rest[: following.start()] if following else rest


def _service_items(html):
    """List items inside the services section, cleaned of markup."""
    section = _services_section(html)
    if not section:
        return []
    items = re.findall(r"<li[^>]*>(.*?)</li>", section, re.I | re.S)
    cleaned = [re.sub(r"<[^>]+>", " ", item) for item in items]
    cleaned = [" ".join(item.split()) for item in cleaned]
    return [item for item in cleaned if 3 <= len(item) <= 60]


class ContactScraper:
    def __init__(self, headless=True):
        """Initialize the scraper with Chrome options"""
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
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
        self.driver.set_page_load_timeout(30)
        self.wait = WebDriverWait(self.driver, 10)
        
        # Email regex pattern
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )
        
        # Phone regex patterns (US and international formats)
        self.phone_patterns = [
            re.compile(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'),  # US format
            re.compile(r'\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}'),  # International
        ]

    def load_csv(self, filename):
        """Load businesses from CSV file"""
        businesses = []
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                businesses.append(row)
        return businesses

    def find_contact_page(self, base_url):
        """Try to find contact page URL"""
        contact_keywords = ['contact', 'contact-us', 'contactus', 'about', 'about-us']
        
        try:
            # First try common contact page patterns
            parsed = urlparse(base_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            
            for keyword in contact_keywords:
                possible_urls = [
                    urljoin(base, f'/{keyword}'),
                    urljoin(base, f'/pages/{keyword}'),
                    urljoin(base, f'/{keyword}.html'),
                    urljoin(base, f'/contact/{keyword}'),
                ]
                
                for url in possible_urls:
                    try:
                        self.driver.get(url)
                        time.sleep(1)
                        
                        # Check if page loaded successfully
                        if self.driver.current_url == url or keyword in self.driver.current_url.lower():
                            return url
                    except:
                        continue
            
            # If no contact page found, try to find contact links on main page
            self.driver.get(base_url)
            time.sleep(2)
            
            links = self.driver.find_elements(By.TAG_NAME, 'a')
            for link in links:
                try:
                    text = link.text.lower()
                    href = link.get_attribute('href')
                    if href and any(keyword in text or keyword in href.lower() for keyword in contact_keywords):
                        return href
                except:
                    continue
                    
        except Exception as e:
            print(f"    Error finding contact page: {str(e)}")
        
        return base_url  # Return base URL if no contact page found

    def extract_emails(self, text):
        """Extract email addresses from text"""
        emails = self.email_pattern.findall(text)
        # Filter out common false positives
        filtered = [
            email for email in emails 
            if not any(x in email.lower() for x in ['example.com', 'placeholder', 'yoursite', 'yourdomain'])
        ]
        return list(set(filtered))  # Remove duplicates

    def extract_phones(self, text):
        """Extract phone numbers from text, one entry per real number.

        The two patterns overlap: the international one also matches the tail
        of a US number, so "(614) 555-0142" came back as both itself and
        "614) 555-0142". De-duplicating on the text kept both, and the broken
        one could end up first — i.e. the number on the call sheet. Match on
        the digits instead, keep the best-punctuated form of each, and return
        them in a stable order (``set`` made the CSV vary between runs).
        """
        spans = []
        for pattern in self.phone_patterns:
            for match in pattern.finditer(text):
                candidate = match.group().strip()
                digits = re.sub(r'\D', '', candidate)
                # E.164 tops out at 15 digits. Anything longer is the
                # international pattern running two numbers together — its
                # separators include whitespace, so "6145550142 6145550199"
                # matches as one twenty-digit "number" that belongs to nobody.
                if 10 <= len(digits) <= 15:
                    spans.append((match.start(), match.end(), candidate, digits))

        def same_number(outer: str, inner: str) -> bool:
            """Whether the longer match is the shorter one with a country code.

            Only then is the inner span a duplicate. Two adjacent numbers
            caught by one greedy match are not the same number, and dropping
            them would lose a real contact.
            """
            return outer.endswith(inner) and len(outer) - len(inner) <= 3

        # The US pattern matches "2079460958" out of "+44 2079460958"; its
        # digits differ, so de-duplication alone would keep both.
        whole = [
            (start, candidate)
            for index, (start, end, candidate, digits) in enumerate(spans)
            if not any(other_start <= start and end <= other_end
                       and (other_end - other_start) > (end - start)
                       and same_number(other_digits, digits)
                       for other, (other_start, other_end, _text, other_digits)
                       in enumerate(spans) if other != index)
        ]

        found = {}
        for start, candidate in whole:
            digits = re.sub(r'\D', '', candidate)
            # Key on every digit, so +44 20 7946 0958 and +33 20 7946 0958 stay
            # two numbers — only the optional North American trunk 1 is the
            # same number written two ways.
            key = digits[1:] if len(digits) == 11 and digits[0] == "1" else digits
            position, best = found.get(key, (start, ""))
            found[key] = (min(position, start),
                          candidate if len(candidate) > len(best) else best)

        # Ordered by where each number appears in the page, not by which regex
        # happened to match it first: the patterns run one after the other, so
        # insertion order would put every US match ahead of an international
        # one printed above it.
        return [candidate for _position, candidate
                in sorted(found.values(), key=lambda item: item[0])]

    def extract_contact_names(self, text):
        """Extract potential contact names from text"""
        # Look for patterns like "Contact: Name" or "Name, Title"
        name_patterns = [
            re.compile(r'(?:Contact|Owner|Manager|Director|CEO|President):\s*([A-Z][a-z]+\s+[A-Z][a-z]+)'),
            re.compile(r'([A-Z][a-z]+\s+[A-Z][a-z]+),\s+(?:Owner|Manager|Director|CEO|President)'),
        ]
        
        names = []
        for pattern in name_patterns:
            matches = pattern.findall(text)
            names.extend(matches)
        
        return list(set(names))

    def scrape_website(self, url):
        """Scrape contact information from a website"""
        contact_info = {
            'emails': [],
            'phones': [],
            'contact_names': []
        }
        
        if not url or url == '':
            return contact_info
        
        try:
            print(f"    Scraping: {url}")
            
            # Try to find contact page
            contact_url = self.find_contact_page(url)
            self.driver.get(contact_url)
            time.sleep(2)
            
            # Get page source
            page_text = self.driver.page_source
            visible_text = self.driver.find_element(By.TAG_NAME, 'body').text
            
            # Extract contact information
            contact_info['emails'] = self.extract_emails(page_text)
            contact_info['phones'] = self.extract_phones(visible_text)
            contact_info['contact_names'] = self.extract_contact_names(visible_text)
            
            # If no contact info found on contact page, try main page
            if not any(contact_info.values()) and contact_url != url:
                self.driver.get(url)
                time.sleep(2)
                page_text = self.driver.page_source
                visible_text = self.driver.find_element(By.TAG_NAME, 'body').text
                
                if not contact_info['emails']:
                    contact_info['emails'] = self.extract_emails(page_text)
                if not contact_info['phones']:
                    contact_info['phones'] = self.extract_phones(visible_text)
                if not contact_info['contact_names']:
                    contact_info['contact_names'] = self.extract_contact_names(visible_text)
            
            # Counted last: `any(contact_info.values())` above decides whether
            # to fall back to the home page, and insights are always truthy.
            contact_info['insights'] = page_insights(page_text, visible_text)
            contact_info['social_links'] = social_links(page_text)

        except TimeoutException:
            print(f"    Timeout loading {url}")
        except WebDriverException as e:
            print(f"    Browser error: {str(e)[:100]}")
        except Exception as e:
            print(f"    Error: {str(e)[:100]}")
        
        return contact_info

    def process_csv(self, input_file):
        """Process all businesses from CSV file"""
        businesses = self.load_csv(input_file)
        results = []
        
        print(f"\nProcessing {len(businesses)} businesses...")
        
        for idx, business in enumerate(businesses):
            print(f"\n[{idx+1}/{len(businesses)}] {business.get('name', 'Unknown')}")
            
            website = business.get('website', '')
            
            # Get contact info from website
            contact_info = self.scrape_website(website)
            
            # Combine with original data
            result = {
                'name': business.get('name', ''),
                'original_phone': business.get('phone', ''),
                'address': business.get('address', ''),
                'website': website,
                'email': ', '.join(contact_info['emails']) if contact_info['emails'] else '',
                'scraped_phone': ', '.join(contact_info['phones']) if contact_info['phones'] else '',
                'contact_name': ', '.join(contact_info['contact_names']) if contact_info['contact_names'] else '',
                'category': business.get('category', ''),
                'rating': business.get('rating', ''),
                'url': business.get('url', ''),
                # Keep the seed search on every row so the export knows which
                # data/<term>/<location>/ folder it belongs in.
                'search_term': business.get('search_term', ''),
                'search_location': business.get('search_location', ''),
            }
            
            results.append(result)
            
            # Show what we found
            if result['email']:
                print(f"    ✓ Email: {result['email']}")
            if result['scraped_phone']:
                print(f"    ✓ Phone: {result['scraped_phone']}")
            if result['contact_name']:
                print(f"    ✓ Contact: {result['contact_name']}")
            if not any([result['email'], result['scraped_phone'], result['contact_name']]):
                print(f"    ✗ No contact info found")
            
            # Small delay to be respectful
            time.sleep(1)
        
        return results

    def save_to_csv(self, results, filename=None):
        """Save results to CSV file.

        With no explicit filename the rows land beside the listings they came
        from, in data/<search term>/<location>/contacts<date>-<time>.csv.
        """
        if not results:
            print("No results to save")
            return None

        if not filename:
            search_term, location = self._search_origin(results)
            path = data_store.export_contacts(results, search_term, location)
        else:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(
                    f, fieldnames=list(data_store.CONTACT_FIELDS),
                    extrasaction='ignore', restval='',
                )
                writer.writeheader()
                writer.writerows(results)

        # Count businesses with contact info
        with_email = sum(1 for r in results if r['email'])
        with_phone = sum(1 for r in results if r['scraped_phone'])
        with_name = sum(1 for r in results if r['contact_name'])

        print(f"\n{'='*60}")
        print(f"✓ Saved {len(results)} businesses to {path}")
        print(f"  - {with_email} with email addresses")
        print(f"  - {with_phone} with scraped phone numbers")
        print(f"  - {with_name} with contact names")
        print(f"{'='*60}")
        return path

    @staticmethod
    def _search_origin(results):
        """The search term / location these rows came from, if the input had it."""
        for row in results:
            term = (row.get('search_term') or '').strip()
            if term:
                return term, (row.get('search_location') or '').strip()
        return 'unspecified', ''

    def save_to_json(self, results, filename=None):
        """Save results to JSON file, alongside the CSV export"""
        if not results:
            print("No results to save")
            return None

        if filename:
            path = Path(filename)
        else:
            search_term, location = self._search_origin(results)
            directory = data_store.search_dir(search_term, location)
            path = directory / data_store.timestamped_name("contacts").replace(".csv", ".json")
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"✓ Saved to {path}")
        return path

    def close(self):
        """Close the browser"""
        self.driver.quit()


def main():
    parser = argparse.ArgumentParser(
        description='Scrape contact details from business websites in CSV file'
    )
    parser.add_argument('csv_file', help='Input CSV file from Google Maps scraper')
    parser.add_argument('--output', default='csv', choices=['csv', 'json', 'both'],
                       help='Output format')
    parser.add_argument('--filename', help='Custom output filename (without extension)')
    parser.add_argument('--headless', action='store_true', default=True,
                       help='Run browser in headless mode')
    parser.add_argument('--visible', action='store_true',
                       help='Run browser in visible mode (opposite of headless)')
    
    args = parser.parse_args()
    
    # Handle headless vs visible mode
    headless = args.headless and not args.visible
    
    scraper = ContactScraper(headless=headless)
    
    try:
        results = scraper.process_csv(args.csv_file)
        
        if args.output in ['csv', 'both']:
            csv_file = f"{args.filename}.csv" if args.filename else None
            scraper.save_to_csv(results, csv_file)
        
        if args.output in ['json', 'both']:
            json_file = f"{args.filename}.json" if args.filename else None
            scraper.save_to_json(results, json_file)
            
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        scraper.close()


if __name__ == "__main__":
    main()
