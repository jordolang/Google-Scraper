# 🚀 Quick Start Guide - Email Generator

Get up and running in under 5 minutes!

## Step 1: Run the Script (30 seconds)

```bash
python3 generate_emails.py
```

That's it! The script will automatically:
- Find your most recent CSV file
- Generate personalized emails for all businesses with email addresses
- Save them in the `generated_emails/` folder

## Step 2: Check the Results (2 minutes)

```bash
open generated_emails/
```

You'll find:
- **Individual HTML files** - One per business
- **`_email_summary.txt`** - List of all generated emails with contact info

## Step 3: Preview an Email (1 minute)

Open any HTML file in your browser to see how it looks:

```bash
open generated_emails/enviro_flow_email.html
```

## Step 4: Send Your First Email (2 minutes)

### Option A: Gmail (Recommended)
1. Open the HTML file in your browser
2. Press `Cmd+A` (Select All), then `Cmd+C` (Copy)
3. Open Gmail and click "Compose"
4. In the compose window, press `Cmd+V` (Paste)
5. Add recipient's email from the summary file
6. Add subject line (suggestions below)
7. Click Send!

### Option B: Any Email Client
1. Open the HTML file in a text editor
2. Copy all the HTML code
3. Use your email client's "Insert HTML" feature
4. Add recipient and subject
5. Send!

## 📧 Subject Line Quick Picks

Copy and customize one of these:

1. **General**: `Transform [Business Name]'s Online Presence`
2. **Direct**: `Custom Website Solution for [Business Name]`
3. **Question**: `Ready to Launch [Business Name] Online?`
4. **Value**: `Professional Website Package for Local Businesses`
5. **Seasonal**: `Limited Availability: Custom Website Packages`

## 🎯 Pro Tips

### Test First
Generate a small batch for testing:

Edit line 346 in `generate_emails.py`:
```python
limit=5  # Instead of limit=None
```

### Skip the Email Requirement
To generate emails for ALL businesses (even without email addresses):

Edit line 345 in `generate_emails.py`:
```python
skip_no_email=False  # Instead of skip_no_email=True
```

### Change Your Email
Edit line 314 in `generate_emails.py`:
```python
FROM_EMAIL = "youremail@example.com"
```

## 📊 Understanding the Output

### Console Output
```
============================================================
Processing: contact_details_20251124_185549.csv
============================================================

⚠️  Skipped (no email): Jc's and Sons Affordable Home Improvements
⚠️  Skipped (no email): Lafferty Construction
✅ Generated: Enviro-Flow
✅ Generated: GMEI Services
...

============================================================
GENERATION COMPLETE
============================================================
Total businesses processed: 50
Emails generated: 15
Skipped (no email): 32
Skipped (no name): 3
Errors: 0
```

### File Structure
```
generated_emails/
├── _email_summary.txt          # Master list with all details
├── enviro_flow_email.html      # Individual email files
├── gmei_services_email.html
├── paul_construction_co_inc_email.html
└── ...
```

## 🎨 Quick Customizations

### Change the Pricing
Edit `email_template.html`:
- Line 264: `<div class="price">$499</div>` (Launchpad)
- Line 284: `<div class="price">Starting at $1,499+</div>` (Professional)
- Line 307: `<div class="price">Custom Pricing</div>` (Enterprise)

### Update Your Email in Template
Edit line 314 in `generate_emails.py`:
```python
FROM_EMAIL = "your@email.com"
```

### Change Brand Colors
Edit `email_template.html`, find and replace:
- `#667eea` → Your primary color
- `#764ba2` → Your secondary color
- `#f5576c` → Your accent color

## ❓ Quick Troubleshooting

### "No CSV files found"
→ Make sure you're in the `Google-Scraper` directory

### "Template not found"
→ Ensure `email_template.html` is in the same folder as the script

### No emails generated
→ Check that your CSV has businesses with email addresses
→ Or set `skip_no_email=False` in the script

### Emails look plain in Gmail
→ Use Gmail's "Paste as rich text" or just paste normally
→ The formatting is embedded in the HTML

## 🎬 What's Next?

1. **Review the emails** - Make sure they look good
2. **Add personal touches** - Customize the opening for important leads
3. **Start sending** - Begin with 5-10 emails per day
4. **Track responses** - Keep a spreadsheet of who you contacted
5. **Follow up** - Send follow-ups 3-5 days later to non-responders

## 📚 Need More Help?

- Read the full documentation: `EMAIL_GENERATOR_README.md`
- Check the example email: Open any generated HTML in your browser
- Customize settings: Edit `email_config.py`

---

**Ready to Go?** Just run:
```bash
python3 generate_emails.py
```

Then open `generated_emails/` and start sending! 🚀

Note: The email's primary call-to-action buttons link to `https://jlang.dev/promo` (exclusive pricing page). General links still point to `https://jlang.dev`.
