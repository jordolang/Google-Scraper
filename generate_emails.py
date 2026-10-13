#!/usr/bin/env python3
"""
Email Generator Script for Jlang.dev Business Outreach
Generates personalized HTML emails from contact_details CSV files
"""

import csv
import html as html_lib
import os
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import data_store
import industries
import pricing_store

# Default directory holding the per-industry templates.
TEMPLATES_DIR = "email_templates"

# Substituted for {{HERO_IMAGE}} when no hero URL is supplied and the template
# has no <!--IF:HERO_IMAGE--> block to drop instead (older, user-edited
# templates). A transparent 1x1 GIF keeps clients from requesting an empty URL.
_TRANSPARENT_PX = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="

# Category words that stay capitalised mid-sentence.
_PROPER_FIRST_WORDS = {
    "american", "asian", "brazilian", "cajun", "caribbean", "chinese", "cuban",
    "ethiopian", "filipino", "french", "german", "greek", "hawaiian", "indian",
    "irish", "italian", "jamaican", "japanese", "korean", "latin", "lebanese",
    "mediterranean", "mexican", "middle", "peruvian", "polish", "spanish",
    "southern", "tex-mex", "thai", "turkish", "vietnamese", "christian",
    "catholic", "baptist",
}

_CONDITIONAL = re.compile(r"<!--IF:([A-Z_]+)-->(.*?)<!--ENDIF:\1-->\n?", re.S)


def apply_conditionals(html, values):
    """Keep ``<!--IF:NAME-->`` blocks whose ``values[NAME]`` is set; drop the rest."""
    return _CONDITIONAL.sub(
        lambda m: m.group(2) if values.get(m.group(1)) else "", html)


def unsubscribe_link(from_email, url=""):
    """Where the footer's Unsubscribe link points: a page if set, else a reply."""
    if url:
        return url
    return f"mailto:{from_email}?subject=Unsubscribe"


class EmailGenerator:
    def __init__(self, template_path=None, output_dir="generated_emails",
                 from_email="jordan@jlang.dev", templates_dir=TEMPLATES_DIR,
                 sender_name="Jordan Lang", sender_address="", unsubscribe_url=""):
        """
        Initialize the email generator

        Two modes:

        * **Legacy single-template** — pass ``template_path`` (e.g. the school
          flow, or the old ``email_template.html``). That one file is loaded
          eagerly and used for every email, exactly as before.
        * **Per-industry** — leave ``template_path`` as ``None``. Each email is
          rendered from ``templates_dir/<industry>.html``, chosen by
          auto-classification or an explicit ``industry_key``.

        Args:
            template_path: Optional path to a single HTML template. When given,
                it overrides per-industry selection (backward compatible).
            output_dir: Directory to save generated emails
            from_email: Sender email address
            templates_dir: Directory of per-industry templates (per-industry mode)
            sender_name: Name the signature signs off with.
            sender_address: Postal address for the footer. US law (CAN-SPAM)
                expects one in commercial email; the line is left out when blank.
            unsubscribe_url: A page that unsubscribes; blank means a mailto
                link that asks the recipient to reply "Unsubscribe".
        """
        self.template_path = template_path
        self.output_dir = output_dir
        self.from_email = from_email
        self.sender_name = sender_name or "Jordan Lang"
        self.sender_address = sender_address or ""
        self.unsubscribe_url = unsubscribe_url or ""
        self.templates_dir = templates_dir
        self._template_cache = {}

        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(exist_ok=True)

        # Eagerly load the single template only in legacy mode.
        self.template = None
        if template_path is not None:
            with open(template_path, 'r', encoding='utf-8') as f:
                self.template = f.read()

    def _load_industry_template(self, industry_key):
        """Load (and cache) the template file for an industry, general fallback."""
        if industry_key in self._template_cache:
            return self._template_cache[industry_key]
        industry = industries.get(industry_key)
        path = Path(self.templates_dir) / industry.template_filename
        if not path.exists():
            # Fall back to the general template rather than crashing a batch.
            path = Path(self.templates_dir) / industries.GENERAL.template_filename
        html = path.read_text(encoding='utf-8')
        self._template_cache[industry_key] = html
        return html

    def industry_for(self, business_data):
        """Classify a business row into an industry key."""
        return industries.classify(
            business_data.get('category', ''), business_data.get('name', '')
        )
    
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
        """A short, neutral note about the business's current website."""
        if self.has_website(website):
            title = "You already have a site, and I can make it work harder."
            body = ("A sharper design, faster load times and clearer calls to "
                    "action usually mean more of your visitors pick up the phone.")
        else:
            title = "I couldn't find a website for you."
            body = ("Most customers look a business up before they call. A simple, "
                    "professional site makes sure they find you, not a competitor.")
        return f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:10px;">
              <tr><td style="padding:16px 18px;">
                <div style="font-size:15px;font-weight:700;color:#111827;padding-bottom:4px;">{title}</div>
                <div style="font-size:14px;line-height:1.65;color:#4b5563;">{body}</div>
              </td></tr>
            </table>
            """

    def generate_email(self, business_data, *, industry_key=None, pricing=None,
                       hero_image=""):
        """
        Generate a personalized email for a business

        Args:
            business_data: Dictionary containing business information
            industry_key: Force a specific industry template. When ``None`` in
                per-industry mode, the business is auto-classified. Ignored in
                legacy single-template mode.
            pricing: Optional ``{field: price}`` dict (e.g. a per-business
                override). Falls back to the industry's stored pricing.
            hero_image: Optional hero-image URL for ``{{HERO_IMAGE}}``.

        Returns:
            Tuple of (email_html, filename, recipient_email)
        """
        # Extract and clean data
        business_name = self.clean_text(business_data.get('name', 'Business Owner'))
        email = self.clean_text(business_data.get('email', '')).split(',')[0].strip()  # Get first email if multiple
        category = self.clean_text(business_data.get('category', 'services'))
        # Maps capitalises categories ("Electrician"); mid-sentence they read
        # better lower-cased. Acronyms ("HVAC contractor") and cuisines
        # ("Mexican restaurant") keep their capital.
        first = category.split(' ', 1)[0].lower()
        if (len(category) > 1 and category[0].isupper() and category[1].islower()
                and first not in _PROPER_FIRST_WORDS):
            category = category[0].lower() + category[1:]
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
        
        # Everything below lands inside HTML; a business called "Smith & Sons"
        # must not break the markup (or inject any).
        esc = lambda value: html_lib.escape(str(value or ''), quote=True)  # noqa: E731

        # Rating info
        rating_info = ''
        if rating:
            try:
                rating_float = float(rating)
                rating_info = f'<div>Rated {esc(rating)}/5 on Google'
                rating_info += ', a reputation worth showing off.</div>' if rating_float >= 4.0 else '.</div>'
            except ValueError:
                pass

        # Contact info
        contact_info = ''
        if phone:
            contact_info += f'<div>Phone: {esc(phone)}</div>'
        if email and '@' in email:
            contact_info += f'<div>Email: {esc(email)}</div>'
        
        # Choose the template. Legacy mode (an explicit template_path) always
        # uses the single loaded template; otherwise pick per-industry.
        if self.template_path is not None and industry_key is None:
            email_html = self.template
            resolved_industry = None
        else:
            resolved_industry = industry_key or self.industry_for(business_data)
            email_html = self._load_industry_template(resolved_industry)

        email_html = apply_conditionals(email_html, {
            'HERO_IMAGE': hero_image,
            'SENDER_ADDRESS': self.sender_address,
        })

        replacements = {
            '{{BUSINESS_NAME}}': esc(business_name),
            '{{CATEGORY}}': esc(category),
            '{{LOCATION}}': esc(location),
            '{{ADDRESS}}': esc(address) if address else 'Your Location',
            '{{CURRENT_WEBSITE_NOTE}}': website_note,
            '{{RATING_INFO}}': rating_info,
            '{{CONTACT_INFO}}': contact_info,
            '{{FROM_EMAIL}}': esc(self.from_email),
            '{{HERO_IMAGE}}': esc(hero_image) if hero_image else _TRANSPARENT_PX,
            '{{SENDER_NAME}}': esc(self.sender_name),
            '{{SENDER_ADDRESS}}': esc(self.sender_address),
            '{{UNSUBSCRIBE_URL}}': esc(unsubscribe_link(self.from_email, self.unsubscribe_url)),
        }

        # Pricing tokens: an explicit override wins, else the industry's stored
        # prices. Harmless no-op on legacy templates that lack the tokens.
        price_row = pricing or pricing_store.prices_for(
            resolved_industry or industries.GENERAL_KEY
        )
        replacements.update(pricing_store.pricing_tokens(price_row))

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
    
    # Find the contact scrapes: the data/<term>/<location>/ exports first, then
    # any legacy contact_details_*.csv left in the working directory.
    csv_files = sorted(
        [p for p in data_store.data_root().rglob('contacts*.csv') if '_demo' not in p.parts]
        + list(Path('.').glob('contact_details_*.csv')),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not csv_files:
        print("❌ No contact CSV files found in data/ or the current directory")
        return

    print("\nAvailable CSV files:")
    for i, csv_file in enumerate(csv_files, 1):
        print(f"{i}. {csv_file}")

    # Use the most recent file by default
    selected_csv = csv_files[0]

    print(f"\n📋 Using most recent file: {selected_csv}")
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
