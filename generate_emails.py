#!/usr/bin/env python3
"""
Email Generator Script for Jlang.dev Business Outreach
Generates personalized HTML emails from contact_details CSV files
"""

import csv
import os
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse


class EmailGenerator:
    def __init__(self, template_path, output_dir="generated_emails", from_email="jordan@jlang.dev"):
        """
        Initialize the email generator
        
        Args:
            template_path: Path to the HTML email template
            output_dir: Directory to save generated emails
            from_email: Sender email address
        """
        self.template_path = template_path
        self.output_dir = output_dir
        self.from_email = from_email
        
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(exist_ok=True)
        
        # Load template
        with open(template_path, 'r', encoding='utf-8') as f:
            self.template = f.read()
    
    def clean_text(self, text):
        """Clean and normalize text data"""
        if not text or text == '':
            return ''
        # Remove extra whitespace and quotes
        text = str(text).strip().strip('"\'')
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        return text
    
    def extract_location(self, address):
        """Extract city from address"""
        if not address:
            return "your area"
        
        # Try to extract city from address (format: "street, city, state zip")
        parts = address.split(',')
        if len(parts) >= 2:
            city = parts[-2].strip()
            # Remove state and zip if present
            city = re.sub(r'\s+[A-Z]{2}\s+\d+.*$', '', city)
            return city
        return "your area"
    
    def format_phone(self, phone):
        """Format phone number"""
        if not phone:
            return None
        
        # Clean the phone number
        phone = re.sub(r'[^\d]', '', str(phone))
        
        # Format as (XXX) XXX-XXXX if 10 digits
        if len(phone) == 10:
            return f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
        elif len(phone) == 11 and phone[0] == '1':
            return f"({phone[1:4]}) {phone[4:7]}-{phone[7:]}"
        
        return phone if phone else None
    
    def has_website(self, website):
        """Check if business has a valid website"""
        if not website:
            return False
        
        website = str(website).strip()
        
        # Filter out Google Maps URLs and similar
        invalid_domains = [
            'google.com',
            'facebook.com',
            'business.google.com',
            'maps.google.com',
            'yelp.com'
        ]
        
        try:
            parsed = urlparse(website)
            domain = parsed.netloc.lower()
            
            # Check if domain contains any invalid domains
            for invalid in invalid_domains:
                if invalid in domain:
                    return False
            
            return True
        except:
            return False
    
    def generate_website_note(self, website):
        """Generate note about current website status"""
        if self.has_website(website):
            return """
            <div style="background-color: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                <p style="margin: 0; color: #856404; font-size: 15px;">
                    <strong>💡 Already Have a Website?</strong><br>
                    I noticed you have an existing website. I can help modernize it with improved design, faster performance, 
                    better SEO, and enhanced functionality to help you reach more customers.
                </p>
            </div>
            """
        else:
            return """
            <div style="background-color: #d1ecf1; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #17a2b8;">
                <p style="margin: 0; color: #0c5460; font-size: 15px;">
                    <strong>🌐 Ready for Your First Website?</strong><br>
                    I noticed you don't currently have a website. In today's market, businesses with a professional 
                    web presence see up to 70% more customer engagement. Let's change that!
                </p>
            </div>
            """
    
    def generate_email(self, business_data):
        """
        Generate a personalized email for a business
        
        Args:
            business_data: Dictionary containing business information
            
        Returns:
            Tuple of (email_html, filename, recipient_email)
        """
        # Extract and clean data
        business_name = self.clean_text(business_data.get('name', 'Business Owner'))
        email = self.clean_text(business_data.get('email', '')).split(',')[0].strip()  # Get first email if multiple
        category = self.clean_text(business_data.get('category', 'services'))
        address = self.clean_text(business_data.get('address', ''))
        website = self.clean_text(business_data.get('website', ''))
        rating = self.clean_text(business_data.get('rating', ''))
        original_phone = self.clean_text(business_data.get('original_phone', ''))
        scraped_phone = self.clean_text(business_data.get('scraped_phone', ''))
        
        # Process data
        location = self.extract_location(address)
        
        # Choose best phone number
        phone = self.format_phone(original_phone if original_phone else scraped_phone.split(',')[0] if scraped_phone else None)
        
        # Generate conditional content
        website_note = self.generate_website_note(website)
        
        # Rating info
        rating_info = ''
        if rating:
            try:
                rating_float = float(rating)
                if rating_float >= 4.0:
                    rating_info = f'<p><strong>⭐ Rating:</strong> {rating}/5.0 - Your excellent reputation shows quality service!</p>'
                else:
                    rating_info = f'<p><strong>⭐ Rating:</strong> {rating}/5.0</p>'
            except:
                pass
        
        # Contact info
        contact_info = ''
        if phone:
            contact_info += f'<p><strong>📞 Phone:</strong> {phone}</p>'
        if email and '@' in email:
            contact_info += f'<p><strong>✉️ Email:</strong> {email}</p>'
        
        # Replace placeholders in template
        email_html = self.template
        replacements = {
            '{{BUSINESS_NAME}}': business_name,
            '{{CATEGORY}}': category,
            '{{LOCATION}}': location,
            '{{ADDRESS}}': address if address else 'Your Location',
            '{{CURRENT_WEBSITE_NOTE}}': website_note,
            '{{RATING_INFO}}': rating_info,
            '{{CONTACT_INFO}}': contact_info,
            '{{FROM_EMAIL}}': self.from_email
        }
        
        for placeholder, value in replacements.items():
            email_html = email_html.replace(placeholder, value)
        
        # Generate filename
        safe_name = re.sub(r'[^\w\s-]', '', business_name.lower())
        safe_name = re.sub(r'[-\s]+', '_', safe_name)
        filename = f"{safe_name}_email.html"
        
        return email_html, filename, email
    
    def process_csv(self, csv_path, skip_no_email=True, limit=None):
        """
        Process a CSV file and generate emails for all businesses
        
        Args:
            csv_path: Path to the contact_details CSV file
            skip_no_email: Skip businesses without email addresses
            limit: Maximum number of emails to generate (None for all)
            
        Returns:
            Dictionary with statistics
        """
        stats = {
            'total': 0,
            'generated': 0,
            'skipped_no_email': 0,
            'skipped_no_name': 0,
            'errors': 0
        }
        
        generated_files = []
        
        print(f"\n{'='*60}")
        print(f"Processing: {csv_path}")
        print(f"{'='*60}\n")
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    stats['total'] += 1
                    
                    # Check if we've reached the limit
                    if limit and stats['generated'] >= limit:
                        print(f"\nReached limit of {limit} emails. Stopping.")
                        break
                    
                    # Skip if no business name
                    if not row.get('name') or row['name'].strip() == '':
                        stats['skipped_no_name'] += 1
                        continue
                    
                    # Skip if no email and skip_no_email is True
                    email = row.get('email', '').strip()
                    if skip_no_email and (not email or '@' not in email):
                        stats['skipped_no_email'] += 1
                        business_name = row.get('name', 'Unknown')
                        print(f"⚠️  Skipped (no email): {business_name}")
                        continue
                    
                    try:
                        # Generate email
                        email_html, filename, recipient_email = self.generate_email(row)
                        
                        # Save to file
                        output_path = os.path.join(self.output_dir, filename)
                        with open(output_path, 'w', encoding='utf-8') as out_f:
                            out_f.write(email_html)
                        
                        stats['generated'] += 1
                        generated_files.append({
                            'business': row.get('name', 'Unknown'),
                            'file': filename,
                            'email': recipient_email if recipient_email and '@' in recipient_email else 'No email',
                            'category': row.get('category', 'N/A')
                        })
                        
                        print(f"✅ Generated: {row.get('name', 'Unknown')}")
                        
                    except Exception as e:
                        stats['errors'] += 1
                        print(f"❌ Error processing {row.get('name', 'Unknown')}: {e}")
        
        except Exception as e:
            print(f"❌ Error reading CSV file: {e}")
            return stats
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"GENERATION COMPLETE")
        print(f"{'='*60}")
        print(f"Total businesses processed: {stats['total']}")
        print(f"Emails generated: {stats['generated']}")
        print(f"Skipped (no email): {stats['skipped_no_email']}")
        print(f"Skipped (no name): {stats['skipped_no_name']}")
        print(f"Errors: {stats['errors']}")
        print(f"\nOutput directory: {self.output_dir}")
        
        # Save summary file
        if generated_files:
            summary_path = os.path.join(self.output_dir, '_email_summary.txt')
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write("EMAIL GENERATION SUMMARY\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*60}\n\n")
                
                for item in generated_files:
                    f.write(f"Business: {item['business']}\n")
                    f.write(f"Category: {item['category']}\n")
                    f.write(f"Email: {item['email']}\n")
                    f.write(f"File: {item['file']}\n")
                    f.write(f"{'-'*60}\n\n")
            
            print(f"\nSummary saved to: {summary_path}")
        
        return stats


def main():
    """Main function to run the email generator"""
    
    # Configuration
    TEMPLATE_PATH = "email_template.html"
    OUTPUT_DIR = "generated_emails"
    FROM_EMAIL = "jordan@jlang.dev"  # Change this to your email
    
    # Pricing information (for reference)
    # Launchpad: $499 | Professional: Starting at $1,499+ | Enterprise: Custom
    
    # Find all contact_details CSV files
    csv_files = sorted(Path('.').glob('contact_details_*.csv'), reverse=True)
    
    if not csv_files:
        print("❌ No contact_details CSV files found in current directory")
        return
    
    print("\nAvailable CSV files:")
    for i, csv_file in enumerate(csv_files, 1):
        print(f"{i}. {csv_file.name}")
    
    # Use the most recent file by default
    selected_csv = csv_files[0]
    
    print(f"\n📋 Using most recent file: {selected_csv.name}")
    print(f"📧 From email: {FROM_EMAIL}")
    print(f"📁 Output directory: {OUTPUT_DIR}")
    
    # Initialize generator
    generator = EmailGenerator(
        template_path=TEMPLATE_PATH,
        output_dir=OUTPUT_DIR,
        from_email=FROM_EMAIL
    )
    
    # Process CSV
    # Set limit=None to generate all emails, or limit=10 to generate only 10 for testing
    stats = generator.process_csv(
        csv_path=str(selected_csv),
        skip_no_email=True,  # Set to False to generate emails even without email addresses
        limit=None  # Set to a number to limit generation for testing
    )
    
    print("\n✨ Done! Check the generated_emails folder for your personalized emails.")


if __name__ == "__main__":
    main()
