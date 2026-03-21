#!/usr/bin/env python3
"""
School Fundraiser Email Generator
Generates personalized Jose Madrid Salsa fundraiser outreach emails
from school athletics contact CSV files.
"""

import csv
import os
import re
from pathlib import Path
from datetime import datetime

from school_config import (
    FUNDRAISER_CONFIG,
    SPORT_PITCHES,
    DEFAULT_PITCH,
    SUBJECT_LINE_TEMPLATES,
    DEFAULT_SUBJECT_STYLE,
    FROM_EMAIL,
    FROM_NAME,
    TEMPLATE_PATH,
    OUTPUT_DIR,
)


class SchoolEmailGenerator:
    def __init__(
        self,
        template_path=None,
        output_dir=None,
        from_email=None,
        from_name=None,
    ):
        """
        Initialize the school email generator.

        Args:
            template_path: Path to the HTML email template
            output_dir: Directory to save generated emails
            from_email: Sender email address
            from_name: Sender display name
        """
        self.template_path = template_path or TEMPLATE_PATH
        self.output_dir = output_dir or OUTPUT_DIR
        self.from_email = from_email or FROM_EMAIL
        self.from_name = from_name or FROM_NAME
        self.fundraiser = FUNDRAISER_CONFIG

        Path(self.output_dir).mkdir(exist_ok=True)

        with open(self.template_path, "r", encoding="utf-8") as f:
            self.template = f.read()

    def clean_text(self, text):
        """Clean and normalize text data"""
        if not text or text == "":
            return ""
        text = str(text).strip().strip("\"'")
        text = re.sub(r"\s+", " ", text)
        return text

    def generate_greeting_name(self, contact_data):
        """Generate appropriate greeting name for the contact"""
        name = self.clean_text(contact_data.get("contact_name", ""))
        title = self.clean_text(contact_data.get("title", ""))

        if name:
            # If name looks like "John Smith", use it with title prefix
            if " " in name and not name.lower().startswith("coach"):
                if "director" in title.lower():
                    return name
                return f"Coach {name.split()[-1]}"
            return name

        if title:
            # Use title as greeting
            if "director" in title.lower():
                return "Athletic Director"
            if "coach" in title.lower():
                return title
            return title

        return "Coaching Staff"

    def generate_sport_pitch(self, sport):
        """Generate sport-specific fundraiser pitch text"""
        if not sport or sport.lower() == "unknown":
            return DEFAULT_PITCH

        sport_lower = sport.lower()
        return SPORT_PITCHES.get(sport_lower, DEFAULT_PITCH)

    def generate_subject_line(self, contact_data):
        """Generate personalized subject line"""
        school_name = self.clean_text(contact_data.get("school_name", "Your School"))
        sport = self.clean_text(contact_data.get("sport", "Athletics"))

        if sport.lower() == "unknown":
            sport = "Athletics"

        templates = list(SUBJECT_LINE_TEMPLATES.values())

        # Deterministic selection based on contact name hash
        name = contact_data.get("contact_name", "") or contact_data.get("school_name", "")
        index = sum(ord(c) for c in name) % len(templates)

        subject = templates[index]
        subject = subject.replace("{school_name}", school_name)
        subject = subject.replace("{sport}", sport)

        return subject

    def generate_email(self, contact_data):
        """
        Generate a personalized fundraiser email.

        Args:
            contact_data: Dictionary with contact information

        Returns:
            Tuple of (email_html, filename, recipient_email)
        """
        # Extract and clean data
        contact_name = self.generate_greeting_name(contact_data)
        email = self.clean_text(contact_data.get("email", "")).split(",")[0].strip()
        sport = self.clean_text(contact_data.get("sport", "Athletics"))
        school_name = self.clean_text(contact_data.get("school_name", "Your School"))
        district = self.clean_text(contact_data.get("district", ""))
        city = self.clean_text(contact_data.get("city", ""))
        state = self.clean_text(contact_data.get("state", ""))
        title = self.clean_text(contact_data.get("title", ""))

        if sport.lower() == "unknown":
            sport = "Athletics"

        sport_pitch = self.generate_sport_pitch(sport)

        # Build replacements
        email_html = self.template
        replacements = {
            "{{CONTACT_NAME}}": contact_name,
            "{{TITLE}}": title if title else "Coach",
            "{{SPORT}}": sport,
            "{{SCHOOL_NAME}}": school_name,
            "{{DISTRICT}}": district if district else city,
            "{{CITY}}": city if city else "your area",
            "{{STATE}}": state,
            "{{SPORT_PITCH}}": sport_pitch,
            "{{FUNDRAISER_PERCENTAGE}}": self.fundraiser["fundraiser_percentage"],
            "{{CTA_URL}}": self.fundraiser["product_url"],
            "{{PRODUCT_URL}}": self.fundraiser["product_url"],
            "{{FROM_EMAIL}}": self.from_email,
            "{{FROM_NAME}}": self.from_name,
        }

        for placeholder, value in replacements.items():
            email_html = email_html.replace(placeholder, value)

        # Generate filename
        safe_school = re.sub(r"[^\w\s-]", "", school_name.lower())
        safe_school = re.sub(r"[-\s]+", "_", safe_school)
        safe_sport = re.sub(r"[^\w\s-]", "", sport.lower())
        safe_sport = re.sub(r"[-\s]+", "_", safe_sport)
        safe_name = re.sub(r"[^\w\s-]", "", contact_name.lower())
        safe_name = re.sub(r"[-\s]+", "_", safe_name)

        filename = f"{safe_school}_{safe_sport}_{safe_name}_email.html"

        return email_html, filename, email

    def process_csv(self, csv_path, skip_no_email=True, limit=None, sports_filter=None):
        """
        Process a CSV file and generate fundraiser emails for all contacts.

        Args:
            csv_path: Path to the school_contacts CSV file
            skip_no_email: Skip contacts without email addresses
            limit: Maximum number of emails to generate
            sports_filter: List of sports to include (None = all)

        Returns:
            Dictionary with statistics
        """
        stats = {
            "total": 0,
            "generated": 0,
            "skipped_no_email": 0,
            "skipped_no_name": 0,
            "skipped_sport_filter": 0,
            "errors": 0,
        }

        generated_files = []

        print(f"\n{'=' * 60}")
        print(f"Processing: {csv_path}")
        print(f"{'=' * 60}\n")

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    stats["total"] += 1

                    if limit and stats["generated"] >= limit:
                        print(f"\nReached limit of {limit} emails. Stopping.")
                        break

                    # Skip if no contact name and no email
                    contact_name = row.get("contact_name", "").strip()
                    email_addr = row.get("email", "").strip()

                    if not contact_name and not email_addr:
                        stats["skipped_no_name"] += 1
                        continue

                    # Skip if no email and skip_no_email is True
                    if skip_no_email and (not email_addr or "@" not in email_addr):
                        stats["skipped_no_email"] += 1
                        school = row.get("school_name", "Unknown")
                        print(f"  Skipped (no email): {school} - {contact_name}")
                        continue

                    # Apply sports filter
                    if sports_filter:
                        sport = row.get("sport", "").lower()
                        if sport not in [s.lower() for s in sports_filter] and sport != "unknown":
                            stats["skipped_sport_filter"] += 1
                            continue

                    try:
                        email_html, filename, recipient_email = self.generate_email(row)

                        output_path = os.path.join(self.output_dir, filename)
                        with open(output_path, "w", encoding="utf-8") as out_f:
                            out_f.write(email_html)

                        stats["generated"] += 1
                        generated_files.append(
                            {
                                "business": row.get("school_name", "Unknown"),
                                "file": filename,
                                "email": recipient_email if recipient_email and "@" in recipient_email else "No email",
                                "category": row.get("sport", "Athletics"),
                            }
                        )

                        school = row.get("school_name", "Unknown")
                        sport = row.get("sport", "Athletics")
                        print(f"  Generated: {school} ({sport}) - {contact_name}")

                    except Exception as e:
                        stats["errors"] += 1
                        print(f"  Error: {row.get('school_name', 'Unknown')}: {e}")

        except Exception as e:
            print(f"  Error reading CSV file: {e}")
            return stats

        # Print summary
        print(f"\n{'=' * 60}")
        print("GENERATION COMPLETE")
        print(f"{'=' * 60}")
        print(f"Total contacts processed: {stats['total']}")
        print(f"Emails generated: {stats['generated']}")
        print(f"Skipped (no email): {stats['skipped_no_email']}")
        print(f"Skipped (no name): {stats['skipped_no_name']}")
        print(f"Skipped (sport filter): {stats['skipped_sport_filter']}")
        print(f"Errors: {stats['errors']}")
        print(f"\nOutput directory: {self.output_dir}")

        # Save summary file (compatible with send_emails.py)
        if generated_files:
            summary_path = os.path.join(self.output_dir, "_email_summary.txt")
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write("EMAIL GENERATION SUMMARY\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'=' * 60}\n\n")

                for item in generated_files:
                    f.write(f"Business: {item['business']}\n")
                    f.write(f"Category: {item['category']}\n")
                    f.write(f"Email: {item['email']}\n")
                    f.write(f"File: {item['file']}\n")
                    f.write(f"{'-' * 60}\n\n")

            print(f"\nSummary saved to: {summary_path}")

        return stats


def main():
    """Main function to run the school email generator"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Jose Madrid Salsa fundraiser emails for school athletics contacts"
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=None,
        help="Input CSV file from school contact scraper (default: most recent)",
    )
    parser.add_argument(
        "--sports",
        default=None,
        help='Comma-separated sports to filter (e.g., "football,basketball")',
    )
    parser.add_argument(
        "--skip-no-email",
        action="store_true",
        default=True,
        help="Skip contacts without email addresses",
    )
    parser.add_argument(
        "--include-no-email",
        action="store_true",
        help="Include contacts even without email addresses",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of emails to generate",
    )
    parser.add_argument(
        "--template",
        default=TEMPLATE_PATH,
        help="Path to email template",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help="Output directory for generated emails",
    )

    args = parser.parse_args()

    # Find CSV file
    if args.csv_file:
        csv_path = args.csv_file
    else:
        csv_files = sorted(Path(".").glob("school_contacts_*.csv"), reverse=True)
        if not csv_files:
            print("No school_contacts CSV files found in current directory")
            return
        csv_path = str(csv_files[0])
        print(f"Using most recent file: {csv_path}")

    skip_no_email = args.skip_no_email and not args.include_no_email
    sports_filter = args.sports.split(",") if args.sports else None

    generator = SchoolEmailGenerator(
        template_path=args.template,
        output_dir=args.output_dir,
    )

    stats = generator.process_csv(
        csv_path=csv_path,
        skip_no_email=skip_no_email,
        limit=args.limit,
        sports_filter=sports_filter,
    )

    print("\nDone! Check the generated_school_emails folder for your fundraiser emails.")


if __name__ == "__main__":
    main()
