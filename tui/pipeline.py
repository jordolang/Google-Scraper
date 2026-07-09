"""Pipeline layer that adapts the existing CLI tools for the TUI.

The TUI never talks to Selenium / SMTP directly.  Instead it goes through a
:class:`Pipeline`, which exposes four coarse steps:

* :meth:`Pipeline.search`           – Google Maps search  -> list[Business]
* :meth:`Pipeline.scrape_contacts`  – visit websites       -> fills contact info
* :meth:`Pipeline.build_message`    – render an email from the HTML template
* :meth:`Pipeline.send`             – deliver the composed emails over SMTP

Every long-running method accepts a ``progress`` callback -- a plain
``Callable[[str], None]`` the caller uses to stream status lines into the UI.

Two implementations are provided:

* :class:`LivePipeline` – the real thing (drives Chrome + SMTP).
* :class:`DemoPipeline` – deterministic sample data so the interface can be
  explored end-to-end with no browser, network, or credentials.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .models import Business, EmailMessage

ProgressFn = Callable[[str], None]


def _noop(_msg: str) -> None:  # pragma: no cover - trivial
    pass


class Pipeline:
    """Common interface shared by the live and demo pipelines."""

    def __init__(
        self,
        *,
        from_email: str = "jordan@jlang.dev",
        template_path: str = "email_template.html",
        headless: bool = True,
    ) -> None:
        self.from_email = from_email
        self.template_path = template_path
        self.headless = headless

    # -- steps ---------------------------------------------------------------
    def search(
        self,
        field: str,
        location: str = "",
        *,
        max_scrolls: int = 8,
        progress: ProgressFn = _noop,
    ) -> List[Business]:
        raise NotImplementedError

    def scrape_contacts(
        self,
        businesses: Sequence[Business],
        *,
        progress: ProgressFn = _noop,
    ) -> List[Business]:
        raise NotImplementedError

    def build_message(self, business: Business) -> EmailMessage:
        raise NotImplementedError

    def send(
        self,
        messages: Sequence[EmailMessage],
        *,
        password: str,
        delay: float = 2.0,
        dry_run: bool = False,
        progress: ProgressFn = _noop,
    ) -> dict:
        raise NotImplementedError


class LivePipeline(Pipeline):
    """Real pipeline backed by Selenium + SMTP.

    Heavy dependencies (Selenium, the scraper modules) are imported lazily so
    the TUI package can be imported – and the demo mode used – on machines
    without a browser driver installed.
    """

    def search(
        self,
        field: str,
        location: str = "",
        *,
        max_scrolls: int = 8,
        progress: ProgressFn = _noop,
    ) -> List[Business]:
        from google_maps_scraper import GoogleMapsScraper

        progress(f"Launching browser ({'headless' if self.headless else 'visible'})…")
        scraper = GoogleMapsScraper(headless=self.headless)
        try:
            progress(f"Searching Google Maps for “{f'{field} {location}'.strip()}”…")
            scraper.search(field, location)
            # Reuse the scraper's URL collection + detail extraction, but stream
            # progress so the UI does not appear frozen.
            progress("Collecting business listings…")
            self._scrape_with_progress(scraper, max_scrolls, progress)
            businesses = [Business.from_dict(b) for b in scraper.businesses]
            progress(f"Found {len(businesses)} businesses.")
            return businesses
        finally:
            scraper.close()

    def _scrape_with_progress(self, scraper, max_scrolls, progress) -> None:
        """Drive ``scraper.scrape_listings`` while emitting progress lines."""
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By

        try:
            scraper.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]'))
            )
        except Exception:
            progress("Results feed did not load in time.")
            return

        urls = scraper._collect_all_business_urls()
        progress(f"Collected {len(urls)} listing links; opening each…")
        for idx, url in enumerate(urls, 1):
            try:
                scraper.driver.get(url)
                time.sleep(2)
                data = scraper._extract_business_details()
                if data:
                    scraper.businesses.append(data)
                    progress(f"[{idx}/{len(urls)}] {data.get('name', 'business')}")
            except Exception as exc:  # pragma: no cover - network dependent
                progress(f"[{idx}/{len(urls)}] error: {str(exc)[:80]}")

    def scrape_contacts(
        self,
        businesses: Sequence[Business],
        *,
        progress: ProgressFn = _noop,
    ) -> List[Business]:
        from contact_scraper import ContactScraper

        progress("Launching browser for website contact scraping…")
        scraper = ContactScraper(headless=self.headless)
        try:
            total = len(businesses)
            for idx, business in enumerate(businesses, 1):
                label = business.name or "business"
                if not business.website:
                    progress(f"[{idx}/{total}] {label}: no website, skipping")
                    business.scanned = True
                    continue
                progress(f"[{idx}/{total}] {label}: scanning {business.website}")
                info = scraper.scrape_website(business.website)
                business.emails = list(info.get("emails", []))
                business.phones = list(info.get("phones", []))
                business.contact_names = list(info.get("contact_names", []))
                business.scanned = True
                if business.emails:
                    progress(f"    ✓ {', '.join(business.emails)}")
                else:
                    progress("    ✗ no email found")
                time.sleep(1)
            return list(businesses)
        finally:
            scraper.close()

    def build_message(self, business: Business) -> EmailMessage:
        from generate_emails import EmailGenerator
        from send_emails import EmailSender

        generator = EmailGenerator(
            template_path=self.template_path,
            output_dir="generated_emails",
            from_email=self.from_email,
        )
        html, _filename, email = generator.generate_email(business.to_generator_row())
        subject = EmailSender(from_email=self.from_email).generate_subject_line(
            business.name, business.category
        )
        to_email = email or business.primary_email
        return EmailMessage(business=business, to_email=to_email, subject=subject, html=html)

    def send(
        self,
        messages: Sequence[EmailMessage],
        *,
        password: str,
        delay: float = 2.0,
        dry_run: bool = False,
        progress: ProgressFn = _noop,
    ) -> dict:
        from send_emails import EmailSender

        sender = EmailSender(from_email=self.from_email)
        stats = {"sent": 0, "failed": 0, "skipped": 0, "total": len(messages)}

        if not dry_run:
            progress(f"Connecting to {sender.smtp_server}:{sender.smtp_port}…")
            if not sender.connect(password):
                progress("❌ SMTP connection/authentication failed.")
                stats["error"] = "authentication failed"
                return stats
            progress("✓ Connected.")

        try:
            for idx, msg in enumerate(messages, 1):
                if not msg.to_email or "@" not in msg.to_email:
                    progress(f"[{idx}/{len(messages)}] {msg.business.name}: no valid address, skipping")
                    stats["skipped"] += 1
                    continue
                if dry_run:
                    progress(f"[{idx}/{len(messages)}] DRY RUN → {msg.to_email}  ({msg.subject})")
                    continue
                progress(f"[{idx}/{len(messages)}] sending → {msg.to_email}…")
                ok = sender.send_email(
                    msg.to_email, msg.subject, msg.html, msg.business.name
                )
                stats["sent" if ok else "failed"] += 1
                if idx < len(messages):
                    time.sleep(delay)
        finally:
            if not dry_run:
                sender.disconnect()
        progress(
            f"Done. sent={stats['sent']} failed={stats['failed']} skipped={stats['skipped']}"
        )
        return stats


class DemoPipeline(Pipeline):
    """Offline pipeline returning canned data – lets you tour the whole flow."""

    _SAMPLE = [
        ("Bright Spark Electric", "Electrician", "4.8", "123 Main St, Columbus, OH 43215",
         "https://brightsparkelectric.example", "(614) 555-0142",
         ["info@brightsparkelectric.example"], ["Dana Rivera"]),
        ("Volt Masters LLC", "Electrical installation service", "4.6",
         "88 Oak Ave, Dublin, OH 43017", "https://voltmasters.example",
         "(614) 555-0199", ["hello@voltmasters.example", "sales@voltmasters.example"],
         ["Chris Nolan"]),
        ("Current Solutions", "Electrician", "4.9", "12 Elm Rd, Westerville, OH 43081",
         "https://currentsolutions.example", "(614) 555-0110",
         ["contact@currentsolutions.example"], []),
        ("Amp & Wire Co.", "Electrical contractor", "4.3",
         "455 Grand Blvd, Columbus, OH 43201", "https://ampandwire.example",
         "(614) 555-0177", [], []),
        ("Reliable Circuit Pros", "Electrician", "5.0",
         "9 Pine St, Hilliard, OH 43026", "", "(614) 555-0155", [], []),
    ]

    def search(
        self,
        field: str,
        location: str = "",
        *,
        max_scrolls: int = 8,
        progress: ProgressFn = _noop,
    ) -> List[Business]:
        progress(f"[demo] pretending to search for “{f'{field} {location}'.strip()}”…")
        businesses: List[Business] = []
        for name, cat, rating, addr, site, phone, _emails, _names in self._SAMPLE:
            time.sleep(0.15)
            b = Business(
                name=name, category=cat, rating=rating, address=addr,
                website=site, phone=phone, reviews_count="42",
                url="https://maps.google.com/?demo",
            )
            businesses.append(b)
            progress(f"  found: {name}")
        progress(f"[demo] found {len(businesses)} businesses.")
        return businesses

    def scrape_contacts(
        self,
        businesses: Sequence[Business],
        *,
        progress: ProgressFn = _noop,
    ) -> List[Business]:
        lookup = {row[0]: row for row in self._SAMPLE}
        total = len(businesses)
        for idx, business in enumerate(businesses, 1):
            time.sleep(0.2)
            row = lookup.get(business.name)
            if row:
                business.emails = list(row[6])
                business.contact_names = list(row[7])
                business.phones = [row[5]] if row[5] else []
            business.scanned = True
            if business.emails:
                progress(f"[{idx}/{total}] {business.name}: ✓ {', '.join(business.emails)}")
            else:
                progress(f"[{idx}/{total}] {business.name}: ✗ no email found")
        return list(businesses)

    def build_message(self, business: Business) -> EmailMessage:
        subject = f"Transform {business.name}'s Online Presence"
        location = business.address.split(",")[1].strip() if "," in business.address else "your area"
        html = (
            "<html><body style='font-family:sans-serif'>"
            f"<p>Hi {business.name},</p>"
            f"<p>I came across {business.name} while looking at {business.category} "
            f"businesses in {location} and wanted to reach out about your website.</p>"
            "<p>I build fast, modern sites for local businesses and would love to help "
            f"{business.name} stand out online.</p>"
            "<p>Best,<br>Jordan Lang<br>jlang.dev</p>"
            "</body></html>"
        )
        return EmailMessage(
            business=business,
            to_email=business.primary_email,
            subject=subject,
            html=html,
        )

    def send(
        self,
        messages: Sequence[EmailMessage],
        *,
        password: str,
        delay: float = 2.0,
        dry_run: bool = False,
        progress: ProgressFn = _noop,
    ) -> dict:
        stats = {"sent": 0, "failed": 0, "skipped": 0, "total": len(messages)}
        mode = "DRY RUN" if dry_run else "demo send"
        progress(f"[demo] {mode} of {len(messages)} email(s)…")
        for idx, msg in enumerate(messages, 1):
            time.sleep(0.2)
            if not msg.to_email or "@" not in msg.to_email:
                progress(f"[{idx}/{len(messages)}] {msg.business.name}: no address, skipped")
                stats["skipped"] += 1
                continue
            progress(f"[{idx}/{len(messages)}] {'would send' if dry_run else 'sent'} → {msg.to_email}")
            if not dry_run:
                stats["sent"] += 1
        progress(
            f"[demo] done. sent={stats['sent']} failed={stats['failed']} skipped={stats['skipped']}"
        )
        return stats


def make_pipeline(
    *,
    demo: bool = False,
    from_email: str = "jordan@jlang.dev",
    template_path: str = "email_template.html",
    headless: bool = True,
) -> Pipeline:
    """Factory returning the appropriate pipeline implementation."""
    cls = DemoPipeline if demo else LivePipeline
    # In demo mode the template may not matter, but keep a sane fallback.
    if not demo and not Path(template_path).exists():
        # Fall back gracefully rather than crashing deep in build_message.
        pass
    return cls(from_email=from_email, template_path=template_path, headless=headless)
