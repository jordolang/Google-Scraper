#!/usr/bin/env python3
"""
Website Contact Scraper
Reads Google Maps CSV results and scrapes contact information from business websites
"""

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
            if host.endswith(social) and url not in found:
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
        # A services section usually lists its offerings; count them so the
        # UI can say "8 services found" rather than just "yes".
        items = re.findall(r"<li[^>]*>(.*?)</li>", html, re.I | re.S)
        listed = [re.sub(r"<[^>]+>", " ", i).strip() for i in items]
        listed = [i for i in listed if 3 <= len(i) <= 60]
        counts["services"] = max(counts["services"], min(len(listed), 40))

    return counts


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
        
        self.driver = webdriver.Chrome(options=options)
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
        """Extract phone numbers from text"""
        phones = []
        for pattern in self.phone_patterns:
            matches = pattern.findall(text)
            phones.extend(matches)
        
        # Clean and deduplicate
        cleaned = []
        for phone in phones:
            # Remove common prefixes and clean
            phone = phone.strip()
            if len(phone) >= 10:  # Minimum valid phone length
                cleaned.append(phone)
        
        return list(set(cleaned))

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
