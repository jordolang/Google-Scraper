#!/usr/bin/env python3
"""
Automated Email Sender for Generated Business Outreach Emails
Sends personalized HTML emails from the generated_emails folder
"""

import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime
import time
import sys


def load_dotenv(path=".env"):
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Existing environment variables win, so an inline `EMAIL_PASSWORD=... python
    send_emails.py` still overrides the file.
    """
    env_file = Path(path)
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class EmailSender:
    def __init__(self, from_email="jordan@jlang.dev", smtp_server=None, smtp_port=None,
                 smtp_username=None, reply_to=None):
        """
        Initialize the email sender

        Args:
            from_email: Sender email address (used in the From: header)
            smtp_server: SMTP server address (auto-detected if None)
            smtp_port: SMTP port (auto-detected if None)
            smtp_username: Username used to authenticate to the SMTP server.
                Defaults to from_email. For an iCloud custom email domain
                (e.g. jlang.dev), this often must be your primary Apple ID
                @icloud.com address, NOT the custom-domain alias.
            reply_to: Address replies should go to, when it differs from the
                From: address. Omitted from the message entirely when unset.
        """
        self.from_email = from_email
        self.smtp_username = smtp_username or from_email
        self.reply_to = reply_to or ""
        self.from_name = "Jordan Lang"
        
        # Auto-detect SMTP settings based on email provider
        if smtp_server is None or smtp_port is None:
            self.smtp_server, self.smtp_port = self._detect_smtp_settings(from_email)
        else:
            self.smtp_server = smtp_server
            self.smtp_port = smtp_port
        
        self.smtp_connection = None
        self.sent_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.failed_emails = []
    
    def _detect_smtp_settings(self, email):
        """Auto-detect SMTP settings based on email domain"""
        domain = email.split('@')[1].lower() if '@' in email else ''
        
        # Common SMTP configurations
        smtp_configs = {
            'gmail.com': ('smtp.gmail.com', 587),
            'outlook.com': ('smtp-mail.outlook.com', 587),
            'hotmail.com': ('smtp-mail.outlook.com', 587),
            'yahoo.com': ('smtp.mail.yahoo.com', 587),
            'icloud.com': ('smtp.mail.me.com', 587),
            'me.com': ('smtp.mail.me.com', 587),
            'mac.com': ('smtp.mail.me.com', 587),
            'jlang.dev': ('smtp.mail.me.com', 587),  # iCloud Mail custom email domain (verified via MX records)
        }
        
        # Try to find matching configuration
        for key, config in smtp_configs.items():
            if key in domain:
                return config
        
        # Default to Gmail settings
        return ('smtp.gmail.com', 587)
    
    def connect(self, password):
        """
        Connect to SMTP server
        
        Args:
            password: Email account password or app password
        """
        try:
            print(f"Connecting to {self.smtp_server}:{self.smtp_port}...")
            self.smtp_connection = smtplib.SMTP(self.smtp_server, self.smtp_port)
            self.smtp_connection.starttls()
            # Normalize: Gmail/iCloud app passwords are shown in 4-char groups
            # separated by spaces or hyphens, but must be sent as 16 raw chars.
            clean_password = password.replace(" ", "").replace("-", "")
            self.smtp_connection.login(self.smtp_username, clean_password)
            print("✅ Successfully connected to SMTP server\n")
            return True
        except smtplib.SMTPAuthenticationError:
            print("\n❌ Authentication failed!")
            print("\nTroubleshooting:")
            print("1. For Gmail/Google Workspace:")
            print("   - Enable 2-Factor Authentication")
            print("   - Create an App Password at: https://myaccount.google.com/apppasswords")
            print("   - Use the App Password instead of your regular password")
            print("\n2. For other providers:")
            print("   - Check if 'Less secure app access' needs to be enabled")
            print("   - Verify your email and password are correct")
            return False
        except Exception as e:
            print(f"❌ Connection failed: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from SMTP server"""
        if self.smtp_connection:
            self.smtp_connection.quit()
            print("\n✅ Disconnected from SMTP server")
    
    def generate_subject_line(self, business_name, category=""):
        """
        Generate personalized subject line for each business
        
        Args:
            business_name: Name of the business
            category: Business category
            
        Returns:
            Personalized subject line
        """
        # Various subject line templates
        templates = [
            f"Transform {business_name}'s Online Presence",
            f"Custom Website Solution for {business_name}",
            f"Elevate {business_name} with a Professional Website",
            f"Website Development Opportunity for {business_name}",
            f"Ready to Launch {business_name} Online?",
        ]
        
        # Select template based on business name hash for consistency
        index = sum(ord(c) for c in business_name) % len(templates)
        return templates[index]
    
    def extract_recipient_info(self, summary_file):
        """
        Extract business information from summary file
        
        Args:
            summary_file: Path to _email_summary.txt
            
        Returns:
            Dictionary mapping filenames to (email, business_name, category)
        """
        recipients = {}
        
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse each business entry
            entries = content.split('------------------------------------------------------------')
            
            for entry in entries:
                if not entry.strip():
                    continue
                
                # Extract fields using regex
                business_match = re.search(r'Business:\s*(.+)', entry)
                category_match = re.search(r'Category:\s*(.+)', entry)
                email_match = re.search(r'Email:\s*(.+)', entry)
                file_match = re.search(r'File:\s*(.+)', entry)
                
                if business_match and email_match and file_match:
                    business_name = business_match.group(1).strip()
                    category = category_match.group(1).strip() if category_match else ""
                    email = email_match.group(1).strip()
                    filename = file_match.group(1).strip()
                    
                    # Validate email
                    if self._is_valid_email(email):
                        recipients[filename] = (email, business_name, category)
        
        except Exception as e:
            print(f"❌ Error reading summary file: {str(e)}")
            return {}
        
        return recipients
    
    def _is_valid_email(self, email):
        """Validate email address format and filter out invalid ones"""
        if not email or '@' not in email:
            return False
        
        # Filter out common invalid patterns
        invalid_patterns = [
            r'\.jpg$',
            r'\.png$',
            r'\.gif$',
            r'\.jpeg$',
            r'@sentry\.wixpress\.com$',  # Wix internal emails
            r'^[a-f0-9]{32}@',  # Hash-like emails
            r'@example\.com$',
            r'@placeholder\.',
            r'@email\.com$',  # Generic placeholder
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, email, re.IGNORECASE):
                return False
        
        # Basic email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, email) is not None
    
    def read_html_email(self, html_file):
        """Read HTML email content from file"""
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"❌ Error reading {html_file}: {str(e)}")
            return None
    
    def send_email(self, to_email, subject, html_content, business_name):
        """
        Send an individual email
        
        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_content: HTML email content
            business_name: Business name (for logging)
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            if self.reply_to:
                msg['Reply-To'] = self.reply_to
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            self.smtp_connection.send_message(msg)
            
            print(f"✅ Sent to {business_name} ({to_email})")
            self.sent_count += 1
            return True
            
        except Exception as e:
            print(f"❌ Failed to send to {business_name} ({to_email}): {str(e)}")
            self.failed_count += 1
            self.failed_emails.append((business_name, to_email, str(e)))
            return False
    
    def send_batch(self, emails_dir="generated_emails", delay=2, dry_run=False, limit=None, skip_list=None):
        """
        Send all emails in the generated_emails directory
        
        Args:
            emails_dir: Directory containing generated email HTML files
            delay: Delay in seconds between emails (to avoid rate limiting)
            dry_run: If True, only show what would be sent without actually sending
            limit: Maximum number of emails to send (None = all)
            skip_list: List of email addresses to skip
            
        Returns:
            Dictionary with sending statistics
        """
        emails_path = Path(emails_dir)
        summary_file = emails_path / "_email_summary.txt"
        
        if not summary_file.exists():
            print(f"❌ Summary file not found: {summary_file}")
            return None
        
        # Extract recipient information
        print("📋 Reading recipient information...")
        recipients = self.extract_recipient_info(summary_file)
        
        if not recipients:
            print("❌ No valid recipients found in summary file")
            return None
        
        print(f"Found {len(recipients)} emails to send\n")
        
        # Filter skip list
        if skip_list:
            skip_set = set(email.lower() for email in skip_list)
            original_count = len(recipients)
            recipients = {
                filename: info for filename, info in recipients.items()
                if info[0].lower() not in skip_set
            }
            skipped = original_count - len(recipients)
            if skipped > 0:
                print(f"⏭️  Skipping {skipped} emails from skip list\n")
                self.skipped_count = skipped
        
        # Apply limit
        if limit and limit < len(recipients):
            print(f"⚠️  Limiting to first {limit} emails\n")
            recipients = dict(list(recipients.items())[:limit])
        
        if dry_run:
            print("🔍 DRY RUN MODE - No emails will be sent\n")
            print("=" * 60)
        
        # Send emails
        start_time = datetime.now()
        
        for idx, (filename, (email, business_name, category)) in enumerate(recipients.items(), 1):
            html_file = emails_path / filename
            
            if not html_file.exists():
                print(f"⚠️  [{idx}/{len(recipients)}] File not found: {filename}")
                self.skipped_count += 1
                continue
            
            # Generate subject line
            subject = self.generate_subject_line(business_name, category)
            
            # Read email content
            html_content = self.read_html_email(html_file)
            if not html_content:
                self.skipped_count += 1
                continue
            
            if dry_run:
                print(f"[{idx}/{len(recipients)}] Would send:")
                print(f"  📧 To: {business_name} ({email})")
                print(f"  📝 Subject: {subject}")
                print(f"  📄 File: {filename}\n")
            else:
                print(f"[{idx}/{len(recipients)}] Sending to {business_name}...")
                self.send_email(email, subject, html_content, business_name)
                
                # Delay between emails (except for last one)
                if idx < len(recipients):
                    time.sleep(delay)
        
        # Summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print("\n" + "=" * 60)
        print("📊 SENDING SUMMARY")
        print("=" * 60)
        print(f"Total emails processed: {len(recipients)}")
        
        if dry_run:
            print(f"Mode: DRY RUN (no emails sent)")
        else:
            print(f"✅ Successfully sent: {self.sent_count}")
            print(f"❌ Failed: {self.failed_count}")
            print(f"⏭️  Skipped: {self.skipped_count}")
            print(f"⏱️  Duration: {duration:.1f} seconds")
            
            if self.failed_emails:
                print("\n❌ Failed emails:")
                for business, email, error in self.failed_emails:
                    print(f"  - {business} ({email}): {error}")
        
        return {
            'sent': self.sent_count,
            'failed': self.failed_count,
            'skipped': self.skipped_count,
            'total': len(recipients),
            'duration': duration
        }


def main():
    """Main function with interactive CLI"""
    print("=" * 60)
    print("📧 AUTOMATED EMAIL SENDER")
    print("=" * 60)
    print()
    
    # Configuration
    # NOTE: jlang.dev is hosted on iCloud Mail (verified via MX records),
    # NOT Google Workspace. SMTP auto-detects smtp.mail.me.com:587.
    from_email = "jordan@jlang.dev"
    emails_dir = "generated_emails"

    # --- Credentials (read from environment — never hardcode secrets) --------
    # Required before sending (not needed for a dry run):
    #   EMAIL_PASSWORD : iCloud app-specific password (from appleid.apple.com)
    #   SMTP_USERNAME  : iCloud SMTP login = primary Apple ID @icloud.com address.
    #                    Mail is still sent *from* jordan@jlang.dev. Defaults to
    #                    from_email if unset.
    #
    #   export SMTP_USERNAME="jordantlang@icloud.com"
    #   export EMAIL_PASSWORD="xxxx-xxxx-xxxx-xxxx"
    load_dotenv()
    hardwired_password = os.environ.get("EMAIL_PASSWORD")
    smtp_username = os.environ.get("SMTP_USERNAME", from_email)

    # Get user input
    print(f"Sender: {from_email}")
    print(f"Emails directory: {emails_dir}")
    print()
    
    # Mode selection
    print("Select mode:")
    print("1. Dry run (preview without sending)")
    print("2. Send all emails")
    print("3. Send limited batch (test)")
    
    mode = input("\nEnter mode (1-3): ").strip()
    
    if mode not in ['1', '2', '3']:
        print("❌ Invalid mode selected")
        return
    
    dry_run = (mode == '1')
    limit = None
    
    if mode == '3':
        limit_input = input("How many emails to send? (e.g., 5): ").strip()
        try:
            limit = int(limit_input)
        except ValueError:
            print("❌ Invalid number")
            return
    
    # Delay configuration
    if not dry_run:
        delay_input = input("\nDelay between emails in seconds (default 2): ").strip()
        delay = float(delay_input) if delay_input else 2.0
    else:
        delay = 0
    
    # Skip list (optional)
    skip_list_input = input("\nEmail addresses to skip (comma-separated, or press Enter): ").strip()
    skip_list = [email.strip() for email in skip_list_input.split(',')] if skip_list_input else None
    
    # Initialize sender
    sender = EmailSender(from_email=from_email, smtp_username=smtp_username)

    # Connect using the env-provided credential if not a dry run
    if not dry_run:
        if not hardwired_password:
            print("\n❌ EMAIL_PASSWORD environment variable is not set.")
            print("   Set your iCloud app-specific password before sending:")
            print('   export SMTP_USERNAME="jordantlang@icloud.com"')
            print('   export EMAIL_PASSWORD="xxxx-xxxx-xxxx-xxxx"')
            return
        print(f"\n🔑 Authenticating as {smtp_username} (sending from {from_email})")
        if not sender.connect(hardwired_password):
            return
    
    print("\n" + "=" * 60)
    print()
    
    # Send emails
    try:
        results = sender.send_batch(
            emails_dir=emails_dir,
            delay=delay,
            dry_run=dry_run,
            limit=limit,
            skip_list=skip_list
        )
        
        if results and not dry_run:
            # Save log
            log_file = f"email_send_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(log_file, 'w') as f:
                f.write(f"Email Send Log\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"=" * 60 + "\n\n")
                f.write(f"Total: {results['total']}\n")
                f.write(f"Sent: {results['sent']}\n")
                f.write(f"Failed: {results['failed']}\n")
                f.write(f"Skipped: {results['skipped']}\n")
                f.write(f"Duration: {results['duration']:.1f}s\n\n")
                
                if sender.failed_emails:
                    f.write("Failed Emails:\n")
                    for business, email, error in sender.failed_emails:
                        f.write(f"  - {business} ({email}): {error}\n")
            
            print(f"\n📄 Log saved to: {log_file}")
    
    finally:
        if not dry_run:
            sender.disconnect()
    
    print("\n✨ Done!")


def _check_licence() -> None:
    """Refuse to run unlicensed, with a message rather than a traceback.

    Running the module directly is a supported way to use this app, so it is
    gated exactly like the desktop screens are. The check hangs off the
    ``__main__`` guard rather than off ``main`` itself, because importing this
    module — which the tests, the TUI and the GUI all do — must never depend
    on a licence.
    """
    from licensing import console, plans

    console.require_or_exit(plans.EMAIL_SEND, action="Sending email")


if __name__ == "__main__":
    try:
        _check_licence()
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)
