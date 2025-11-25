# 📧 Jlang.dev Email Marketing System

A complete email marketing solution for generating personalized HTML email templates for potential website development clients.

## 📁 Files Included

- **`email_template.html`** - Professional, fully responsive HTML email template
- **`generate_emails.py`** - Python script to generate personalized emails from CSV data
- **`EMAIL_GENERATOR_README.md`** - This file (documentation)

## ✨ Features

### Email Template Features
- 🎨 **Professional Design** - Modern gradient design with Jlang.dev branding
- 📱 **Fully Responsive** - Looks great on desktop, tablet, and mobile devices
- 🎯 **Three-Tier Pricing** - Launchpad ($499), Professional ($1,499+), and Enterprise (Custom)
- 💼 **Personalized Content** - Dynamically populated business information
- ⭐ **Smart Customization** - Shows different messages based on existing website status
- 📊 **Rating Integration** - Displays Google ratings when available
- 🔗 **Multiple CTAs** - Clear call-to-action buttons for scheduling consultations

### Python Script Features
- 🤖 **Automated Generation** - Process entire CSV files automatically
- 📝 **Data Cleaning** - Handles malformed data, extra spaces, and special characters
- 🔍 **Smart Detection** - Identifies existing websites and adjusts messaging
- 📞 **Phone Formatting** - Automatically formats phone numbers (XXX) XXX-XXXX
- 📧 **Email Validation** - Filters out invalid email addresses
- 📊 **Progress Reporting** - Real-time console feedback during generation
- 📋 **Summary Report** - Generates detailed summary of all created emails

## 🚀 Quick Start

### Step 1: Run the Generator

```bash
python3 generate_emails.py
```

The script will:
1. Find the most recent `contact_details_*.csv` file
2. Process all businesses with valid email addresses
3. Generate personalized HTML emails
4. Save them to the `generated_emails/` folder

Note: The primary CTAs in the email now link to `https://jlang.dev/promo`, which contains the exclusive email-only pricing and form to claim the discount. General references to Jlang.dev still link to the main site.

### Step 2: Review Generated Emails

Check the `generated_emails/` folder for:
- Individual HTML email files (one per business)
- `_email_summary.txt` - Complete list of generated emails with details

### Step 3: Send Emails

Open each HTML file in your browser to preview, then:
1. Copy the HTML content
2. Paste into your email client (Gmail, Outlook, etc.)
3. Add the recipient's email address from the summary file
4. Customize subject line (suggestions below)
5. Send!

## ⚙️ Configuration Options

### Customize the Script

Open `generate_emails.py` and modify these variables in the `main()` function:

```python
# Your email address (appears in footer)
FROM_EMAIL = "jordan@jlang.dev"

# Output directory for generated emails
OUTPUT_DIR = "generated_emails"

# Template file path
TEMPLATE_PATH = "email_template.html"
```

### Processing Options

When calling `process_csv()`, you can adjust:

```python
generator.process_csv(
    csv_path=str(selected_csv),
    skip_no_email=True,    # False to generate even without emails
    limit=None              # Set to 10 for testing, None for all
)
```

## 🎨 Customizing the Email Template

### Update Branding

Edit `email_template.html`:

1. **Change Colors**: Find and replace hex codes
   - Primary: `#667eea` (purple-blue)
   - Secondary: `#764ba2` (purple)
   - Accent: `#f5576c` (coral-pink)

2. **Update Pricing**: Search for "Launchpad Package", "Professional Package", "Enterprise Package"
   - Launchpad: $499 (24-hour turnaround)
   - Professional: Starting at $1,499+ (5-25 pages)
   - Enterprise: Custom Pricing (full-service solution)

3. **Modify Features**: Edit the `<ul class="features">` lists under each package

4. **Change CTAs**: Update button text and links (search for `class="cta-button"`)

### Add Your Logo

Replace the emoji in the header:

```html
<div class="header">
    <h1>🚀 Jlang.dev</h1>
    <!-- Or replace with: -->
    <img src="YOUR_LOGO_URL" alt="Jlang.dev" style="max-width: 200px;">
</div>
```

## 📋 Email Template Variables

The template uses these placeholders (automatically replaced by the script):

| Variable | Description | Example |
|----------|-------------|---------|
| `{{BUSINESS_NAME}}` | Company name | "ABC Construction" |
| `{{CATEGORY}}` | Business category | "General contractor" |
| `{{LOCATION}}` | Extracted city | "Zanesville" |
| `{{ADDRESS}}` | Full address | "123 Main St, Zanesville, OH 43701" |
| `{{CURRENT_WEBSITE_NOTE}}` | Website status message | Conditional note about existing site |
| `{{RATING_INFO}}` | Google rating | "⭐ Rating: 4.5/5.0" |
| `{{CONTACT_INFO}}` | Phone/email | Formatted contact details |
| `{{FROM_EMAIL}}` | Your email | "jordan@jlang.dev" |

## 💡 Suggested Email Subject Lines

Choose based on the business category and approach:

### General Approaches
- "Transform [Business Name]'s Online Presence"
- "Custom Website Solution for [Business Name]"
- "Helping [Business Name] Reach More Customers Online"
- "Professional Website Package for [Category] Businesses"

### For Businesses Without Websites
- "Ready to Launch [Business Name] Online?"
- "Your Business Deserves a Professional Website"
- "Let's Get [Business Name] on the Web"

### For Businesses With Existing Sites
- "Upgrade [Business Name]'s Website - Free Consultation"
- "Modernize Your Online Presence"
- "Is Your Website Working Hard Enough?"

### Urgency/Seasonal
- "Limited Availability: Custom Website Packages"
- "Spring Special: Website Development for Local Businesses"
- "New Year, New Website for [Business Name]"

## 📊 Understanding the CSV Data

The script expects CSV files with these columns:

- `name` - Business name (required)
- `email` - Email address (required unless skip_no_email=False)
- `category` - Business type (e.g., "Contractor", "Plumber")
- `address` - Physical address
- `website` - Existing website URL
- `rating` - Google rating (0-5)
- `original_phone` - Phone from Google
- `scraped_phone` - Phone from website scraping

## 🔧 Troubleshooting

### "No contact_details CSV files found"
- Ensure you're running the script from the Google-Scraper directory
- Check that CSV files follow the naming pattern: `contact_details_*.csv`

### "Error reading CSV file"
- Verify the CSV file isn't corrupted
- Check that it has the correct column headers
- Try opening in a text editor to inspect formatting

### Emails not generating
- Check that businesses have email addresses in the CSV
- Set `skip_no_email=False` to generate for all businesses
- Check console output for specific error messages

### Template not found
- Ensure `email_template.html` is in the same directory as the script
- Update `TEMPLATE_PATH` if you moved the template

## 📈 Best Practices

### Email Sending
1. **Start Small**: Test with 5-10 emails first
2. **Personalize Further**: Add a custom opening line for each email
3. **Timing**: Send Tuesday-Thursday, 10am-2pm for best open rates
4. **Follow Up**: Wait 3-5 days before sending a follow-up
5. **Track Results**: Keep notes on responses and conversions

### Compliance
- ✅ Include unsubscribe option (already in template footer)
- ✅ Use your real contact information
- ✅ Don't send to purchased lists (use your own scraped data)
- ✅ Honor unsubscribe requests immediately
- ✅ Comply with CAN-SPAM Act and GDPR if applicable

### Content Customization
- Review each email before sending
- Add personal touches based on business specifics
- Research the business briefly for better context
- Adjust pricing recommendations based on business size

## 🎯 Advanced Usage

### Generate Test Batch

```python
# In generate_emails.py, modify the process_csv call:
stats = generator.process_csv(
    csv_path=str(selected_csv),
    skip_no_email=True,
    limit=5  # Only generate 5 emails for testing
)
```

### Process Specific CSV File

```python
# Instead of auto-selecting the most recent:
selected_csv = "contact_details_20251124_185549.csv"

generator.process_csv(
    csv_path=selected_csv,
    skip_no_email=True,
    limit=None
)
```

### Generate for All Businesses (Even Without Email)

```python
stats = generator.process_csv(
    csv_path=str(selected_csv),
    skip_no_email=False,  # Generate even without email
    limit=None
)
```

Useful for:
- Printing and mailing physical letters
- Manual email lookup later
- Complete record of all businesses

## 📞 Next Steps

1. **Test the System**
   ```bash
   python3 generate_emails.py
   ```

2. **Review Outputs**
   - Open a few generated HTML files in your browser
   - Check the `_email_summary.txt` file
   - Verify data looks correct

3. **Customize if Needed**
   - Update your email address in the script
   - Adjust pricing in the template
   - Modify design colors/branding

4. **Start Sending**
   - Begin with businesses you're most interested in
   - Track responses in a spreadsheet
   - Refine your approach based on feedback

## 💬 Support

For issues or questions:
- Check the console output for error messages
- Review this README carefully
- Test with a small batch first (limit=5)

## 📝 License

This email system is custom-built for Jlang.dev business development.
Feel free to modify for your own use.

---

**Created for Jlang.dev** | Custom Web Development & Digital Solutions
