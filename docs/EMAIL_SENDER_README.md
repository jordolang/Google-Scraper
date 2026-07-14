# 📧 Automated Email Sender Guide

Comprehensive guide for using the automated email sender to deliver your generated business outreach emails.

## 🚀 Quick Start

```bash
# Run the email sender
python send_emails.py
```

The script will guide you through an interactive setup process.

## 📋 Prerequisites

### 1. Generated Emails
Make sure you have generated emails in the `generated_emails/` folder:
```bash
python generate_emails.py
```

### 2. Gmail App Password (IMPORTANT!)

**For jordan@jlang.dev (Google Workspace):**

You **must** use an App Password, not your regular password.

#### How to Create an App Password:

1. Visit: https://myaccount.google.com/apppasswords
2. Sign in with your Google account
3. Select app: **Mail**
4. Select device: **Mac** (or your device)
5. Click **Generate**
6. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)
7. Use this password when the script prompts you

**Note**: You need 2-Factor Authentication enabled to create App Passwords.

## 🎯 Features

### ✨ Personalized Subject Lines
Each email gets a unique subject line based on the business name:
- "Transform [Business Name]'s Online Presence"
- "Custom Website Solution for [Business Name]"
- "Elevate [Business Name] with a Professional Website"
- "Website Development Opportunity for [Business Name]"
- "Ready to Launch [Business Name] Online?"

### 🛡️ Email Validation
Automatically filters out invalid email addresses:
- Image files (.jpg, .png, etc.)
- Wix internal emails (@sentry.wixpress.com)
- Hash-like placeholder emails
- Generic placeholders (info@email.com)

### 📊 Sending Modes

#### 1. Dry Run (Preview)
Preview what emails would be sent without actually sending them:
```bash
python send_emails.py
# Select mode: 1
```

#### 2. Send All Emails
Send all valid emails in the `generated_emails/` folder:
```bash
python send_emails.py
# Select mode: 2
```

#### 3. Send Limited Batch (Test)
Send a limited number of emails for testing:
```bash
python send_emails.py
# Select mode: 3
# Enter: 5 (or any number)
```

### ⚙️ Configuration Options

#### Delay Between Emails
Default: 2 seconds
- Prevents rate limiting
- Customizable during setup
- Recommended: 2-5 seconds

#### Skip List
Skip specific email addresses:
```bash
# When prompted, enter comma-separated emails:
info@example.com, test@test.com
```

## 📖 Usage Guide

### Step-by-Step Walkthrough

1. **Run the script**:
   ```bash
   python send_emails.py
   ```

2. **Select mode**:
   ```
   Select mode:
   1. Dry run (preview without sending)
   2. Send all emails
   3. Send limited batch (test)
   
   Enter mode (1-3): 1
   ```

3. **Configure delay** (if sending):
   ```
   Delay between emails in seconds (default 2): 3
   ```

4. **Skip list** (optional):
   ```
   Email addresses to skip (comma-separated, or press Enter): 
   [Press Enter to skip none]
   ```

5. **Enter App Password** (if sending):
   ```
   ⚠️  IMPORTANT: For Gmail/Google Workspace:
      Use an App Password, not your regular password
      Generate at: https://myaccount.google.com/apppasswords
   
   Enter password for jordan@jlang.dev: ****
   ```

6. **Review results**:
   ```
   ============================================================
   📊 SENDING SUMMARY
   ============================================================
   Total emails processed: 20
   ✅ Successfully sent: 18
   ❌ Failed: 0
   ⏭️  Skipped: 2
   ⏱️  Duration: 45.2 seconds
   
   📄 Log saved to: email_send_log_20251125_081234.txt
   ```

## 📁 Output Files

### Email Send Log
After sending, a log file is created:
```
email_send_log_20251125_081234.txt
```

Contents:
```
Email Send Log
Date: 2025-11-25 08:12:34
============================================================

Total: 20
Sent: 18
Failed: 0
Skipped: 2
Duration: 45.2s

Failed Emails:
  (none)
```

## 🔧 Advanced Usage

### Using as a Module

```python
from send_emails import EmailSender

# Initialize sender
sender = EmailSender(from_email="jordan@jlang.dev")

# Connect with App Password
sender.connect("your-app-password-here")

# Send batch with custom options
results = sender.send_batch(
    emails_dir="generated_emails",
    delay=3,
    dry_run=False,
    limit=10,
    skip_list=["skip@example.com"]
)

# Disconnect
sender.disconnect()

print(f"Sent: {results['sent']}")
print(f"Failed: {results['failed']}")
```

### Custom SMTP Configuration

```python
sender = EmailSender(
    from_email="your@email.com",
    smtp_server="smtp.yourserver.com",
    smtp_port=587
)
```

## 🛡️ Best Practices

### 1. Always Test First
Start with a dry run or small batch:
```bash
# Dry run
python send_emails.py  # Select mode 1

# Small test batch
python send_emails.py  # Select mode 3, then enter 5
```

### 2. Respect Rate Limits
- Use 2-5 second delays between emails
- Don't send more than 100 emails per day initially
- Monitor for any delivery issues

### 3. Monitor Deliverability
- Check your email's Sent folder
- Look for bounce-back messages
- Review the log file for failures

### 4. Warm Up Your Email
If this is a new email account:
- Day 1: Send 5-10 emails
- Day 2: Send 10-20 emails
- Day 3+: Gradually increase
- Monitor spam complaints

### 5. Clean Your List
Before sending:
- Remove obviously fake emails
- Remove competitors
- Remove duplicate entries

## ⚠️ Troubleshooting

### Authentication Failed

**Error**: `❌ Authentication failed!`

**Solutions**:
1. **Use App Password**, not regular password
   - Visit: https://myaccount.google.com/apppasswords
   - Enable 2FA first if not enabled
   - Generate new App Password

2. **Copy password correctly**
   - No spaces when entering
   - All 16 characters

3. **Check account status**
   - Ensure account is active
   - Check for security alerts

### Connection Failed

**Error**: `❌ Connection failed: [error message]`

**Solutions**:
1. Check internet connection
2. Verify SMTP settings
3. Check firewall settings
4. Try different network

### Invalid Recipients

**Message**: `❌ No valid recipients found`

**Solutions**:
1. Check `_email_summary.txt` exists
2. Verify emails have valid format
3. Re-run `generate_emails.py`

### Rate Limited

**Symptoms**: Emails fail after some succeed

**Solutions**:
1. Increase delay between emails
2. Reduce batch size
3. Wait 24 hours before resuming
4. Check Google Workspace sending limits

### Emails Going to Spam

**Solutions**:
1. **SPF/DKIM/DMARC**: Verify your domain's email authentication
2. **Warm up**: Start with small batches
3. **Content**: Avoid spam trigger words
4. **Engagement**: Send to engaged recipients
5. **Unsubscribe**: Include opt-out link (already in template)

## 📊 Email Statistics

### Typical Success Rates
- **Valid emails**: 85-95% delivery
- **Invalid/bounced**: 5-10%
- **Spam filtered**: 5-15% (varies by recipient)

### Sending Limits (Google Workspace)
- **Free Gmail**: 500 emails/day
- **Google Workspace**: 2,000 emails/day
- **Recommended**: Start with 50-100/day

## 🔒 Security & Privacy

### What Gets Logged
- Business names
- Email addresses
- Send success/failure status
- Error messages

### What Doesn't Get Logged
- Your password (never stored)
- Email content
- Personal data

### Data Protection
- Logs stored locally only
- No cloud uploads
- Delete logs after reviewing

## 📝 Legal & Ethics

### CAN-SPAM Compliance
✅ **This script includes**:
- Valid sender address
- Accurate subject lines
- Unsubscribe mechanism (in template)
- Physical address (in template)

⚠️ **You must**:
- Honor unsubscribe requests within 10 days
- Include your physical business address
- Use accurate "From" information
- Identify message as advertisement

### GDPR Compliance (if applicable)
- Verify you have legitimate interest
- Provide opt-out mechanism
- Respect data subject rights
- Maintain records of consent

### Best Practices
- Only email relevant prospects
- Don't purchase email lists
- Respect opt-outs immediately
- Monitor spam complaints
- Be transparent about your service

## 🎯 Pro Tips

### 1. Segment Your Sends
Send different categories on different days:
```bash
# Day 1: Contractors
# Day 2: Interior designers
# Day 3: Plumbers
```

### 2. Track Responses
Create a simple spreadsheet:
```
Business Name | Email | Sent Date | Response | Status
```

### 3. Follow Up
- Wait 3-5 days after first email
- Send polite follow-up if no response
- Don't send more than 2 follow-ups

### 4. Test Subject Lines
- Try different subject line styles
- Track which get better responses
- Adjust `generate_subject_line()` function

### 5. Monitor Sender Reputation
- Use tools like https://mxtoolbox.com
- Check blacklist status
- Monitor bounce rates

## 🆘 Support

### Common Questions

**Q: Can I use a different email address?**
A: Yes, edit line 368 in `send_emails.py`:
```python
from_email = "your@email.com"
```

**Q: Can I customize subject lines?**
A: Yes, edit the `generate_subject_line()` function (lines 102-124)

**Q: How do I stop mid-send?**
A: Press `Ctrl+C` - already-sent emails won't be resent

**Q: Can I resume a failed batch?**
A: Yes, use the skip list to exclude already-sent addresses

**Q: Does this work with Outlook/Yahoo?**
A: Yes, SMTP settings auto-detect. You may need different app passwords.

## 📞 Contact

For questions or issues:
- Review this documentation
- Check the main README.md
- Open an issue on GitHub
- Visit https://jlang.dev

---

**Version**: 1.0
**Last Updated**: November 2024
**Author**: Jordan Lang (@jordolang)

🎉 **Happy Sending!**
