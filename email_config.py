"""
Email Generator Configuration
Customize these settings to match your needs
"""

# ==================== SENDER INFORMATION ====================

# Your email address (appears in email footer)
FROM_EMAIL = "jordan@jlang.dev"

# Your business name
BUSINESS_NAME = "Jlang.dev"

# Your website URL
WEBSITE_URL = "https://jlang.dev"

# Promo page URL (exclusive for email recipients)
PROMO_URL = "https://jlang.dev/promo"

# Services page URL (general public)
SERVICES_URL = "https://jlang.dev/services"


# ==================== FILE PATHS ====================

# Email template file
TEMPLATE_PATH = "email_template.html"

# Output directory for generated emails
OUTPUT_DIR = "generated_emails"

# CSV file to process (None = use most recent)
# Example: "contact_details_20251124_185549.csv"
CSV_FILE = None


# ==================== GENERATION OPTIONS ====================

# Skip businesses without email addresses
SKIP_NO_EMAIL = True

# Maximum number of emails to generate (None = all)
# Set to a number like 10 for testing
GENERATION_LIMIT = None


# ==================== PRICING (for template customization) ====================

# Launchpad package price (introductory tier)
LAUNCHPAD_PRICE = "$499"

# Professional package price  
PROFESSIONAL_PRICE = "Starting at $1,499+"

# Enterprise package pricing text
ENTERPRISE_PRICE = "Custom Pricing"


# ==================== EMAIL SUBJECT LINE TEMPLATES ====================

# Choose your preferred subject line style or customize
SUBJECT_LINE_TEMPLATES = {
    'default': "Transform {business_name}'s Online Presence",
    'direct': "Custom Website Solution for {business_name}",
    'question': "Ready to Launch {business_name} Online?",
    'value': "Professional Website Package for {category} Businesses",
    'seasonal': "Limited Availability: Custom Website Packages",
}

# Default subject line to use
DEFAULT_SUBJECT_STYLE = 'default'


# ==================== FILTERING OPTIONS ====================

# Filter by minimum rating (None = no filter)
# Example: 4.0 = only businesses with 4+ stars
MIN_RATING = None

# Filter by category (None = all categories)
# Example: ["Contractor", "General contractor", "Plumber"]
CATEGORY_FILTER = None

# Exclude businesses with these keywords in their name
EXCLUDE_KEYWORDS = [
    # Add business names to skip, e.g.:
    # "franchise name",
    # "chain store",
]


# ==================== ADVANCED OPTIONS ====================

# Include businesses without websites
INCLUDE_NO_WEBSITE = True

# Include businesses with existing websites
INCLUDE_HAS_WEBSITE = True

# Verbose output (more detailed console messages)
VERBOSE = True


# ==================== DO NOT EDIT BELOW THIS LINE ====================

def get_config():
    """Return configuration as a dictionary"""
    return {
        'from_email': FROM_EMAIL,
        'business_name': BUSINESS_NAME,
        'website_url': WEBSITE_URL,
        'promo_url': PROMO_URL,
        'services_url': SERVICES_URL,
        'template_path': TEMPLATE_PATH,
        'output_dir': OUTPUT_DIR,
        'csv_file': CSV_FILE,
        'skip_no_email': SKIP_NO_EMAIL,
        'generation_limit': GENERATION_LIMIT,
        'launchpad_price': LAUNCHPAD_PRICE,
        'professional_price': PROFESSIONAL_PRICE,
        'enterprise_price': ENTERPRISE_PRICE,
        'subject_line_templates': SUBJECT_LINE_TEMPLATES,
        'default_subject_style': DEFAULT_SUBJECT_STYLE,
        'min_rating': MIN_RATING,
        'category_filter': CATEGORY_FILTER,
        'exclude_keywords': EXCLUDE_KEYWORDS,
        'include_no_website': INCLUDE_NO_WEBSITE,
        'include_has_website': INCLUDE_HAS_WEBSITE,
        'verbose': VERBOSE,
    }
