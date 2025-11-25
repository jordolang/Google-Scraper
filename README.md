# 🔍 Google Maps Business Scraper & Email Generator

A comprehensive Python-based toolkit for scraping business information from Google Maps and generating personalized outreach emails. Perfect for local business prospecting, lead generation, and automated email campaigns.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Selenium](https://img.shields.io/badge/selenium-4.15+-green.svg)](https://selenium-python.readthedocs.io/)

## 📋 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Usage](#-usage)
  - [Scraping Google Maps](#1-scraping-google-maps)
  - [Scraping Contact Details](#2-scraping-contact-details)
  - [Generating Emails](#3-generating-emails)
  - [Sending Emails](#4-sending-emails)
- [Project Components](#-project-components)
- [Output Examples](#-output-examples)
- [Configuration](#-configuration)
- [Documentation](#-documentation)
- [Legal & Ethics](#-legal--ethics)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

## ✨ Features

### 🗺️ Google Maps Scraping
- Extract comprehensive business data from Google Maps search results
- Collect: names, addresses, phone numbers, websites, ratings, reviews, categories
- Configurable headless/visible browser mode
- Automatic scroll pagination for bulk collection
- CSV and JSON export formats

### 📧 Contact Information Scraping
- Intelligent website contact page detection
- Extract emails, phone numbers, and contact names from business websites
- Multiple phone format support (US and international)
- Smart regex patterns with false-positive filtering
- Batch processing of Google Maps results

### 💌 Email Generator
- Generate personalized HTML emails from scraped data
- Beautiful, responsive email templates with gradient designs
- Three-tier pricing packages (Launchpad, Professional, Enterprise)
- Automated email personalization using business names
- Batch email generation with summary reports
- Professional HTML formatting for direct copy-paste into Gmail

### 📤 Automated Email Sender
- Send generated emails automatically via SMTP
- Personalized subject lines for each business
- Intelligent email validation and filtering
- Dry run mode for testing
- Rate limiting and delay configuration
- Detailed sending logs and statistics
- Support for Gmail, Google Workspace, and other providers

### 🛠️ Additional Tools
- CSV to HTML table converter
- HTML to PDF converter
- Automated file organization by timestamp

## 🚀 Quick Start

Get up and running in under 5 minutes!

```bash
# 1. Clone the repository
git clone https://github.com/jordolang/Google-Scraper.git
cd Google-Scraper

# 2. Install dependencies
pip install -r requirements.txt

# 3. Scrape Google Maps for businesses
python google_maps_scraper.py "plumbers" --location "New York, NY"

# 4. Scrape contact details from websites
python contact_scraper.py google_maps_results_*.csv

# 5. Generate personalized emails
python generate_emails.py

# 6. Send emails automatically
python send_emails.py
```

📖 **See [QUICK_START.md](QUICK_START.md) for detailed step-by-step instructions!**

## 📦 Installation

### Prerequisites
- Python 3.7 or higher
- Google Chrome browser
- ChromeDriver (automatically managed by Selenium 4.15+)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/jordolang/Google-Scraper.git
   cd Google-Scraper
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify installation**
   ```bash
   python google_maps_scraper.py --help
   ```

## 📖 Usage

### 1. Scraping Google Maps

#### Basic Usage
```bash
# Search for businesses in a specific location
python google_maps_scraper.py "restaurants" --location "San Francisco, CA"

# Coffee shops in Boston
python google_maps_scraper.py "coffee shops" --location "Boston, MA"

# Local gyms
python google_maps_scraper.py "gyms" --location "Chicago, IL"
```

#### Advanced Options
```bash
# Custom output filename
python google_maps_scraper.py "dentists" --location "Los Angeles" --filename dental_leads

# Export to JSON format
python google_maps_scraper.py "plumbers" --location "Seattle" --output json

# Export to both CSV and JSON
python google_maps_scraper.py "electricians" --location "Portland" --output both

# Visible browser mode (debugging)
python google_maps_scraper.py "hotels" --location "Miami" --visible

# Increase scroll depth for more results
python google_maps_scraper.py "contractors" --location "Austin" --max-scrolls 20
```

#### Command-Line Arguments
| Argument | Required | Description | Default |
|----------|----------|-------------|---------|
| `search_term` | Yes | What to search for (e.g., "restaurants") | - |
| `--location` | No | Location to search in | - |
| `--output` | No | Output format: `csv`, `json`, or `both` | `csv` |
| `--filename` | No | Custom output filename (no extension) | Auto-generated |
| `--visible` | No | Run browser in visible mode | False |
| `--max-scrolls` | No | Maximum scrolls to load results | 10 |

#### Output Fields
The scraper collects the following data for each business:
- **name**: Business name
- **rating**: Star rating (e.g., "4.5")
- **reviews_count**: Number of reviews
- **category**: Business category/type
- **address**: Full address
- **phone**: Phone number
- **website**: Business website URL
- **plus_code**: Google Plus Code location
- **hours**: Operating hours
- **url**: Google Maps URL

### 2. Scraping Contact Details

Extract detailed contact information from business websites:

```bash
# Process the most recent Google Maps CSV
python contact_scraper.py google_maps_results_20251119_060637.csv

# Specify custom output filename
python contact_scraper.py google_maps_results.csv --output my_contacts

# Run with visible browser (debugging)
python contact_scraper.py results.csv --visible

# Export to JSON
python contact_scraper.py results.csv --format json
```

#### What It Extracts
- **Emails**: All valid email addresses found on the website
- **Phone Numbers**: Additional phone numbers beyond Google Maps data
- **Contact Names**: Owner, manager, or contact person names
- **Contact Page URLs**: Direct links to contact pages

### 3. Generating Emails

Generate beautiful, personalized HTML emails from your contact data:

```bash
# Generate emails from the most recent contact CSV
python generate_emails.py

# The script automatically:
# - Finds your most recent CSV file
# - Generates personalized emails
# - Saves them in generated_emails/ folder
# - Creates a summary report
```

#### Email Features
- **Professional Design**: Gradient backgrounds, modern styling
- **Responsive Layout**: Mobile-friendly HTML templates
- **Three Pricing Tiers**:
  - 🚀 **Launchpad**: $499 - Basic website package
  - 💼 **Professional**: $1,499+ - Full custom website
  - 🏢 **Enterprise**: Custom - Complete solution
- **Personalization**: Automatically inserts business names
- **Call-to-Action**: Links to exclusive pricing page

#### Customization
Edit `email_config.py` to customize:
```python
FROM_EMAIL = "your@email.com"
FROM_NAME = "Your Name"
SUBJECT_LINE = "Your Custom Subject"
```

Edit `email_template.html` to change:
- Pricing amounts
- Service descriptions
- Colors and branding
- Footer information

### 4. Sending Emails

Automatically send generated emails via SMTP:

```bash
# Run the email sender (interactive mode)
python send_emails.py

# The script will guide you through:
# 1. Select mode (dry run, send all, or limited batch)
# 2. Configure delay between emails
# 3. Optional skip list
# 4. Enter email password (use App Password for Gmail)
```

#### Sending Modes

**1. Dry Run (Preview)**
- Preview emails without sending
- See recipients and subject lines
- Test your configuration

**2. Send All Emails**
- Send all valid emails in `generated_emails/`
- Automatically filters invalid addresses
- Creates detailed log file

**3. Send Limited Batch (Test)**
- Send a specified number of emails
- Perfect for testing
- Example: Send first 5 emails

#### Features
- **Personalized Subject Lines**: Each business gets a unique subject
- **Email Validation**: Filters out invalid/placeholder emails
- **Rate Limiting**: Configurable delay between sends
- **Sending Logs**: Detailed logs of all sent emails
- **Error Handling**: Graceful handling of failures
- **SMTP Auto-Detection**: Works with Gmail, Google Workspace, Outlook, etc.

#### Gmail/Google Workspace Setup

**Important**: Use an App Password, not your regular password!

1. Enable 2-Factor Authentication
2. Visit: https://myaccount.google.com/apppasswords
3. Generate an App Password
4. Use this password when prompted by the script

**See [EMAIL_SENDER_README.md](EMAIL_SENDER_README.md) for complete documentation!**

## 🗂️ Project Components

```
Google-Scraper/
├── 📄 google_maps_scraper.py      # Main Google Maps scraper
├── 📄 contact_scraper.py          # Website contact scraper
├── 📄 generate_emails.py          # Email generator
├── 📄 send_emails.py              # Automated email sender
├── 📄 email_template.html         # HTML email template
├── 📄 email_config.py             # Email configuration
├── 📄 csv_to_table.py             # CSV to HTML converter
├── 📄 html_to_pdf.py              # HTML to PDF converter
├── 📄 requirements.txt            # Python dependencies
├── 📄 README.md                   # This file
├── 📄 QUICK_START.md              # Quick start guide
├── 📄 EMAIL_GENERATOR_README.md   # Email generator docs
├── 📄 EMAIL_SENDER_README.md      # Email sender docs
├── 📄 PRICING_BREAKDOWN.md        # Pricing structure
├── 📄 EXCLUSIVE_OFFERS_GUIDE.md   # Offers documentation
├── 📄 LINK_STRUCTURE.md           # Link architecture
└── 📁 generated_emails/           # Output directory
```

## 📊 Output Examples

### Google Maps Scraper Output
**File**: `google_maps_results_20251119_060637.csv`

```csv
name,rating,reviews_count,category,address,phone,website,url
"Joe's Pizza","4.5","250","Pizza restaurant","123 Main St, New York, NY 10001","(212) 555-1234","https://joespizza.com","https://maps.google.com/..."
"Best Plumbing","4.8","89","Plumber","456 Oak Ave, Brooklyn, NY 11201","(718) 555-5678","https://bestplumbing.com","https://maps.google.com/..."
```

### Contact Scraper Output
**File**: `contact_details_20251119_060637.csv`

```csv
name,website,google_phone,emails,additional_phones,contact_names
"Joe's Pizza","https://joespizza.com","(212) 555-1234","info@joespizza.com, catering@joespizza.com","(212) 555-1235",""
"Best Plumbing","https://bestplumbing.com","(718) 555-5678","contact@bestplumbing.com","(718) 555-5679, (718) 555-5680","John Smith"
```

### Email Generator Output
**File**: `generated_emails/joes_pizza_email.html`

Beautiful HTML email with:
- Personalized greeting: "Hi Joe's Pizza Team,"
- Professional service offerings
- Three-tier pricing structure
- Call-to-action buttons
- Contact information
- Responsive design

## ⚙️ Configuration

### Email Settings
Edit `email_config.py`:
```python
# Your contact information
FROM_EMAIL = "your@email.com"
FROM_NAME = "Your Name"
PHONE = "(555) 123-4567"
WEBSITE = "https://yourwebsite.com"

# Email settings
SUBJECT_LINE = "Transform Your Business Online"
```

### Scraper Settings
Edit the Python files directly or use command-line arguments:
```python
# In google_maps_scraper.py
max_scrolls = 10        # Number of times to scroll
headless = True         # Run browser in background
timeout = 10            # Seconds to wait for elements

# In contact_scraper.py
page_load_timeout = 30  # Seconds to wait for page load
```

## 📚 Documentation

- **[QUICK_START.md](QUICK_START.md)** - Get started in 5 minutes
- **[EMAIL_GENERATOR_README.md](EMAIL_GENERATOR_README.md)** - Detailed email generator guide
- **[EMAIL_SENDER_README.md](EMAIL_SENDER_README.md)** - Automated email sending guide
- **[PRICING_BREAKDOWN.md](PRICING_BREAKDOWN.md)** - Service pricing structure
- **[EXCLUSIVE_OFFERS_GUIDE.md](EXCLUSIVE_OFFERS_GUIDE.md)** - Special offers documentation
- **[LINK_STRUCTURE.md](LINK_STRUCTURE.md)** - URL and link architecture

## ⚖️ Legal & Ethics

**IMPORTANT**: This tool is provided for educational purposes only.

### Legal Considerations
- ⚠️ Web scraping may violate Google's Terms of Service
- 🔒 Always respect robots.txt and website terms
- 📧 Comply with CAN-SPAM Act and GDPR for email campaigns
- 🚦 Be mindful of rate limiting and server load
- 📜 Consider using official APIs when available

### Best Practices
- ✅ Use data responsibly and ethically
- ✅ Only contact businesses that are relevant to your services
- ✅ Provide clear opt-out mechanisms in emails
- ✅ Respect privacy and data protection laws
- ✅ Don't spam or overload servers with requests
- ✅ Test with small batches before scaling

### Disclaimer
**You are responsible for ensuring your use of this tool complies with all applicable laws and terms of service.** The author assumes no liability for misuse.

## 🐛 Troubleshooting

### ChromeDriver Errors
```bash
# Make sure Chrome browser is installed
# Selenium 4.15+ manages ChromeDriver automatically
pip install --upgrade selenium
```

### No Results Found
```bash
# Run with visible browser to debug
python google_maps_scraper.py "search term" --visible

# Try increasing delays in code
# Check if Google is blocking automated access
```

### Missing Contact Information
- Some businesses may not have all fields available
- Empty strings are returned for missing data
- Use `--visible` flag to see what the scraper sees

### Email Generation Issues
```bash
# Ensure template exists
ls email_template.html

# Check CSV file has email column
head -n 1 contact_details_*.csv

# Run from project root directory
cd /path/to/Google-Scraper
python generate_emails.py
```

### Common Issues

**"No module named 'selenium'"**
```bash
pip install -r requirements.txt
```

**"Template file not found"**
```bash
# Make sure you're in the project directory
cd /Users/jordanlang/Repos/Google-Scraper
```

**"No CSV files found"**
```bash
# Check you have results files in the directory
ls *.csv
```

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Commit your changes**
   ```bash
   git commit -m "Add amazing feature"
   ```
4. **Push to the branch**
   ```bash
   git push origin feature/amazing-feature
   ```
5. **Open a Pull Request**

### Areas for Contribution
- 🐛 Bug fixes and error handling improvements
- 🎨 Email template designs
- 📖 Documentation enhancements
- 🔧 Additional scraping features
- 🌐 International format support
- ⚡ Performance optimizations

## 📝 License

This project is licensed under the MIT License - see below for details:

```
MIT License

Copyright (c) 2024 Jordan Lang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 👤 Author

**Jordan Lang**
- GitHub: [@jordolang](https://github.com/jordolang)
- Website: [jlang.dev](https://jlang.dev)

## 🌟 Show Your Support

If this project helped you, please give it a ⭐️!

## 📞 Contact

For questions, suggestions, or support:
- Open an issue on GitHub
- Visit [jlang.dev](https://jlang.dev)

---

**Made with ❤️ for automating business outreach**

*Last Updated: November 2024*
