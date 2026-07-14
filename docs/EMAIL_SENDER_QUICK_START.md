# 📧 Email Sender - Quick Start

## 🚀 Send Your Emails in 3 Steps

### Step 1: Generate App Password (One-time setup)

**For jordan@jlang.dev (Google Workspace):**

1. Visit: https://myaccount.google.com/apppasswords
2. Sign in with your Google account
3. Select app: **Mail**
4. Select device: **Mac**
5. Click **Generate**
6. **Copy the 16-character password** (e.g., `abcd efgh ijkl mnop`)
7. Save it somewhere safe!

### Step 2: Test with Dry Run

```bash
cd /Users/jordanlang/Repos/Google-Scraper
python send_emails.py
```

When prompted:
- Select mode: **1** (Dry run)
- Press Enter for skip list
- Review the preview

### Step 3: Send Your First Batch

```bash
python send_emails.py
```

When prompted:
- Select mode: **3** (Limited batch)
- Enter number: **5** (start small!)
- Delay: **3** (3 seconds between emails)
- Press Enter for skip list
- Enter your **App Password** (from Step 1)

## 📊 What You'll See

```
============================================================
📧 AUTOMATED EMAIL SENDER
============================================================

Sender: jordan@jlang.dev
Emails directory: generated_emails

Select mode:
1. Dry run (preview without sending)
2. Send all emails
3. Send limited batch (test)

Enter mode (1-3): 3
How many emails to send? (e.g., 5): 5

Delay between emails in seconds (default 2): 3

Email addresses to skip (comma-separated, or press Enter): 

⚠️  IMPORTANT: For Gmail/Google Workspace:
   Use an App Password, not your regular password
   Generate at: https://myaccount.google.com/apppasswords

Enter password for jordan@jlang.dev: ****

Connecting to smtp.gmail.com:587...
✅ Successfully connected to SMTP server

============================================================

📋 Reading recipient information...
Found 24 emails to send

⚠️  Limiting to first 5 emails

[1/5] Sending to Enviro-Flow...
✅ Sent to Enviro-Flow (enviro@enviro-flow.com)
[2/5] Sending to Covic Connection...
✅ Sent to Covic Connection (sales@covicconnection.com)
[3/5] Sending to Paul Construction Co Inc...
✅ Sent to Paul Construction Co Inc (kgraham@paulconstruction.net)
[4/5] Sending to Modern Glass Paint & Tile Co...
✅ Sent to Modern Glass Paint & Tile Co (paintdept@sbcglobal.net)
[5/5] Sending to Lepi Enterprises Inc....
✅ Sent to Lepi Enterprises Inc. (jim@lepienterprises.com)

============================================================
📊 SENDING SUMMARY
============================================================
Total emails processed: 5
✅ Successfully sent: 5
❌ Failed: 0
⏭️  Skipped: 0
⏱️  Duration: 15.3 seconds

📄 Log saved to: email_send_log_20251125_082345.txt

✅ Disconnected from SMTP server

✨ Done!
```

## 📝 Example Subject Lines Generated

The script automatically creates personalized subject lines:

- "Transform Enviro-Flow's Online Presence"
- "Custom Website Solution for Covic Connection"
- "Elevate Paul Construction Co Inc with a Professional Website"
- "Website Development Opportunity for Modern Glass Paint & Tile Co"
- "Ready to Launch Lepi Enterprises Inc. Online?"

## ✅ Best Practices

### For Your First Send
1. ✅ Start with **dry run** (mode 1)
2. ✅ Send **5 emails** as a test (mode 3)
3. ✅ Check your **Sent folder** to verify
4. ✅ Wait **3-5 seconds** between emails
5. ✅ Monitor for any bounce-backs

### Daily Sending Schedule
- **Day 1**: Send 5-10 emails
- **Day 2**: Send 10-20 emails  
- **Day 3**: Send 20-30 emails
- **Day 4+**: Send up to 50-100 per day

### Rate Limiting
- **Minimum delay**: 2 seconds
- **Recommended delay**: 3-5 seconds
- **Google Workspace limit**: 2,000/day
- **Start conservative**: 50-100/day

## 🛡️ Filtered Emails

The script automatically skips invalid emails:
- ✅ Skipped: `details-window-shower-rendering@2x-scaled.jpg` (image file)
- ✅ Skipped: `c183baa23371454f99f417f6616b724d@sentry.wixpress.com` (Wix internal)
- ✅ Skipped: `info@email.com` (generic placeholder)

## 📁 What Gets Created

After sending, you'll have:
```
email_send_log_20251125_082345.txt
```

Example log:
```
Email Send Log
Date: 2025-11-25 08:23:45
============================================================

Total: 5
Sent: 5
Failed: 0
Skipped: 0
Duration: 15.3s
```

## 🔥 Common Commands

### Dry Run (Preview)
```bash
python send_emails.py
# Select: 1
```

### Send 5 Test Emails
```bash
python send_emails.py
# Select: 3
# Enter: 5
```

### Send All Valid Emails
```bash
python send_emails.py
# Select: 2
```

### Skip Specific Emails
```bash
python send_emails.py
# When prompted for skip list:
# bad@example.com, test@test.com
```

## ⚠️ Troubleshooting

### "Authentication failed"
- ✅ Use **App Password**, not regular password
- ✅ Remove spaces when entering password
- ✅ Regenerate App Password if needed

### "No valid recipients found"
- ✅ Run `python generate_emails.py` first
- ✅ Check that `generated_emails/_email_summary.txt` exists

### Emails going to spam
- ✅ Start with small batches (5-10)
- ✅ Warm up your email account gradually
- ✅ Increase delay between emails (5+ seconds)

## 📞 Need Help?

See the full documentation:
```bash
# Main README
cat README.md

# Email sender guide
cat EMAIL_SENDER_README.md
```

---

**Quick Reference Card**

| Mode | Description | When to Use |
|------|-------------|-------------|
| 1 | Dry run | First time, testing |
| 2 | Send all | Full campaign |
| 3 | Limited batch | Testing, daily limits |

**Recommended Settings**
- First send: Mode 3, 5 emails, 3s delay
- Daily send: Mode 3, 50 emails, 3s delay
- Full send: Mode 2, 3s delay

🎉 **You're ready to send!**
