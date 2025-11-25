#!/usr/bin/env python3
"""
Google Maps Business Scraper
Scrapes business information including names, addresses, phone numbers, websites, etc.
"""

import time
import csv
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import argparse


class GoogleMapsScraper:
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
        self.wait = WebDriverWait(self.driver, 10)
        self.businesses = []

    def search(self, search_term, location=""):
        """Search for businesses on Google Maps"""
        query = f"{search_term} {location}".strip()
        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
        
        print(f"Searching for: {query}")
        self.driver.get(url)
        time.sleep(3)
        
        # Scroll to load more results
        self._scroll_results()

    def _scroll_results(self, max_scrolls=10):
        """Scroll through the results panel to load more businesses"""
        try:
            scrollable_div = self.driver.find_element(By.CSS_SELECTOR, 
                'div[role="feed"]')
            
            for i in range(max_scrolls):
                self.driver.execute_script(
                    'arguments[0].scrollTop = arguments[0].scrollHeight', 
                    scrollable_div
                )
                time.sleep(2)
                print(f"Scrolled {i+1}/{max_scrolls}")
                
        except NoSuchElementException:
            print("Could not find scrollable results")

    def _click_with_retry(self, element, max_retries=3):
        """Click an element with retry logic for stale elements"""
        for attempt in range(max_retries):
            try:
                # Try scrolling element into view first
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.5)
                # Click using JavaScript to avoid interception issues
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except StaleElementReferenceException:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    # Need to re-find the element in the calling function
                    return False
                else:
                    print("  Element became stale after retries")
                    return False
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    print(f"  Click failed: {str(e)}")
                    return False
        return False

    def scrape_listings(self):
        """Scrape all visible business listings"""
        try:
            # Wait for results to load
            self.wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div[role="feed"]')
            ))
            
            # Collect all business URLs first (more stable than working with elements)
            business_urls = self._collect_all_business_urls()
            
            print(f"Found {len(business_urls)} businesses")
            
            # Process each business by URL
            for idx, url in enumerate(business_urls):
                try:
                    print(f"Scraping business {idx+1}/{len(business_urls)}")
                    
                    # Navigate directly to the business URL
                    self.driver.get(url)
                    time.sleep(2)
                    
                    # Extract business details
                    business_data = self._extract_business_details()
                    if business_data:
                        self.businesses.append(business_data)
                    
                except Exception as e:
                    print(f"Error scraping business {idx+1}: {str(e)}")
                    continue
                    
        except TimeoutException:
            print("Timeout waiting for results")

    def _collect_all_business_urls(self):
        """Collect all unique business URLs from the search results"""
        urls = set()
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
                        if href and href not in urls:
                            urls.add(href)
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
        
        return list(urls)

    def _extract_business_details(self):
        """Extract details from a business listing page"""
        data = {}
        
        try:
            # Business name
            try:
                name = self.driver.find_element(By.CSS_SELECTOR, 
                    'h1.DUwDvf').text
                data['name'] = name
            except:
                data['name'] = ''
            
            # Rating
            try:
                rating = self.driver.find_element(By.CSS_SELECTOR, 
                    'div.F7nice span[aria-hidden="true"]').text
                data['rating'] = rating
            except:
                data['rating'] = ''
            
            # Number of reviews
            try:
                reviews = self.driver.find_element(By.CSS_SELECTOR, 
                    'div.F7nice span[aria-label*="reviews"]').text
                data['reviews_count'] = reviews.strip('()')
            except:
                data['reviews_count'] = ''
            
            # Category
            try:
                category = self.driver.find_element(By.CSS_SELECTOR, 
                    'button.DkEaL').text
                data['category'] = category
            except:
                data['category'] = ''
            
            # Address
            try:
                address = self.driver.find_element(By.CSS_SELECTOR, 
                    'button[data-item-id="address"]').text
                data['address'] = address
            except:
                data['address'] = ''
            
            # Phone
            try:
                phone = self.driver.find_element(By.CSS_SELECTOR, 
                    'button[data-item-id^="phone"]').text
                data['phone'] = phone
            except:
                data['phone'] = ''
            
            # Website
            try:
                website = self.driver.find_element(By.CSS_SELECTOR, 
                    'a[data-item-id="authority"]').get_attribute('href')
                data['website'] = website
            except:
                data['website'] = ''
            
            # Plus Code
            try:
                plus_code = self.driver.find_element(By.CSS_SELECTOR, 
                    'button[data-item-id="oloc"]').text
                data['plus_code'] = plus_code
            except:
                data['plus_code'] = ''
            
            # Hours
            try:
                hours_button = self.driver.find_element(By.CSS_SELECTOR, 
                    'button[data-item-id="oh"]')
                data['hours'] = hours_button.get_attribute('aria-label')
            except:
                data['hours'] = ''
            
            # URL
            data['url'] = self.driver.current_url
            
            print(f"  ✓ {data['name']}")
            return data
            
        except Exception as e:
            print(f"Error extracting details: {str(e)}")
            return None

    def save_to_csv(self, filename=None):
        """Save scraped data to CSV file"""
        if not filename:
            filename = f"google_maps_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        if not self.businesses:
            print("No data to save")
            return
        
        keys = ['name', 'rating', 'reviews_count', 'category', 'address', 
                'phone', 'website', 'plus_code', 'hours', 'url']
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.businesses)
        
        print(f"\n✓ Saved {len(self.businesses)} businesses to {filename}")

    def save_to_json(self, filename=None):
        """Save scraped data to JSON file"""
        if not filename:
            filename = f"google_maps_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        if not self.businesses:
            print("No data to save")
            return
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.businesses, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Saved {len(self.businesses)} businesses to {filename}")

    def close(self):
        """Close the browser"""
        self.driver.quit()


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
        scraper.search(args.search_term, args.location)
        scraper.scrape_listings()
        
        if args.output in ['csv', 'both']:
            csv_file = f"{args.filename}.csv" if args.filename else None
            scraper.save_to_csv(csv_file)
        
        if args.output in ['json', 'both']:
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
