"""Pipeline layer that adapts the existing CLI tools for the TUI.

The TUI never talks to Selenium / SMTP directly.  Instead it goes through a
:class:`Pipeline`, which exposes four coarse steps:

* :meth:`Pipeline.search`           – Google Maps search  -> list[Business]
* :meth:`Pipeline.scrape_contacts`  – visit websites       -> fills contact info
* :meth:`Pipeline.build_message`    – render an email from the HTML template
* :meth:`Pipeline.send`             – deliver the composed emails over SMTP

Every long-running method accepts a ``progress`` callback -- a plain
``Callable[[str], None]`` the caller uses to stream status lines into the UI.
:meth:`Pipeline.scrape_contacts` additionally accepts ``on_event``, which
receives a :class:`~tui.models.ScanEvent` per business as it starts and
finishes, so the UI can drive a progress bar and live result counters.

Two implementations are provided:

* :class:`LivePipeline` – the real thing (drives Chrome + SMTP).
* :class:`DemoPipeline` – deterministic sample data so the interface can be
  explored end-to-end with no browser, network, or credentials.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import data_store

from .models import Business, EmailMessage, ScanEvent

ProgressFn = Callable[[str], None]
ScanFn = Callable[[ScanEvent], None]
BusinessFn = Callable[["Business"], None]


def _noop(_msg: str) -> None:  # pragma: no cover - trivial
    pass


def _noop_event(_event: "ScanEvent") -> None:  # pragma: no cover - trivial
    pass


def _noop_business(_business: "Business") -> None:  # pragma: no cover - trivial
    pass


class Pipeline:
    """Common interface shared by the live and demo pipelines."""

    def __init__(
        self,
        *,
        from_email: str = "jordan@jlang.dev",
        template_path: str = "email_template.html",
        headless: bool = True,
        data_root: Optional[Path] = None,
        templates_dir: str = "email_templates",
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_username: Optional[str] = None,
        reply_to: str = "",
        scan_delay: float = 1.0,
        max_results: int = 0,
    ) -> None:
        self.from_email = from_email
        # SMTP details, when the account needs more than the address implies —
        # an iCloud custom domain authenticates as the Apple ID that owns it,
        # not as the alias in the From: header. Left as None, EmailSender
        # infers server and port from the address as before.
        self.smtp_server = smtp_server or None
        self.smtp_port = smtp_port or None
        self.smtp_username = smtp_username or None
        self.reply_to = reply_to
        # Seconds to wait between websites, and the cap on listings per search
        # (0 = no cap). Both are surfaced in the desktop app's settings.
        self.scan_delay = max(0.0, scan_delay)
        self.max_results = max(0, int(max_results))
        self.template_path = template_path
        # Directory of per-industry templates the email generator renders from.
        self.templates_dir = templates_dir
        self.headless = headless
        # Where CSV exports land; ``None`` means data_store's default data/ dir.
        self.data_root = data_root
        # The query behind the current run, so the contact scan knows which
        # data/<term>/<location>/ folder its CSV belongs in.
        self.search_term = ""
        self.search_location = ""
        self.last_listings_csv: Optional[Path] = None
        self.last_contacts_csv: Optional[Path] = None

    # -- exports -------------------------------------------------------------
    def _remember_search(
        self, businesses: Sequence[Business], field: str, location: str
    ) -> None:
        """Stamp the seed query onto the run and onto every row it produced."""
        self.search_term = field
        self.search_location = location
        for business in businesses:
            business.search_term = business.search_term or field
            business.search_location = business.search_location or location

    def _origin(self, businesses: Sequence[Business]) -> tuple[str, str]:
        """The search a set of businesses came from, however it reached us."""
        for business in businesses:
            if business.search_term:
                return business.search_term, business.search_location
        return self.search_term or "unspecified", self.search_location

    def export_listings(
        self, businesses: Sequence[Business], *, progress: ProgressFn = _noop
    ) -> Optional[Path]:
        """Write the search results to data/<term>/<location>/listings*.csv."""
        term, location = self._origin(businesses)
        path = data_store.export_listings(
            [b.to_listing_row() for b in businesses], term, location, base=self.data_root
        )
        self.last_listings_csv = path
        if path:
            progress(f"💾 Saved {len(businesses)} listing(s) → {path}")
        return path

    def export_contacts(
        self, businesses: Sequence[Business], *, progress: ProgressFn = _noop
    ) -> Optional[Path]:
        """Write the scanned contact info to data/<term>/<location>/contacts*.csv."""
        # Anything we scanned, plus anything a phone lookup filled in — a
        # business the scan drew a blank on still belongs in the export once
        # Google or Yellow Pages gives us a number.
        scanned = [b for b in businesses if b.scanned or b.has_contact_info]
        if not scanned:
            return None
        term, location = self._origin(scanned)
        path = data_store.export_contacts(
            [b.to_contact_row() for b in scanned], term, location, base=self.data_root
        )
        self.last_contacts_csv = path

        # Fold the contact info back into the listings file so one CSV per
        # search carries the whole story.
        data_store.update_listings(
            self.last_listings_csv,
            {
                data_store.row_key(b.name): {
                    "name": b.name,
                    "email": ", ".join(b.emails),
                    "contact_name": ", ".join(b.contact_names),
                    "scraped_phone": ", ".join(b.phones),
                    "phone_source": b.phone_source,
                }
                for b in scanned
                if b.name
            },
        )
        # Reported only once both files are written, so an interrupted run can
        # never be cut off between the two.
        if path:
            progress(f"💾 Saved contacts for {len(scanned)} business(es) → {path}")
        return path

    def record_outreach(
        self, messages: Sequence[EmailMessage], *, progress: ProgressFn = _noop
    ) -> Optional[Path]:
        """Mark delivered emails on the listings CSV and on the businesses.

        A business logged here is treated as already contacted: it carries the
        recipient, the timestamp and the template on its listings row, and the
        sales-call queue skips it from then on.
        """
        delivered = [m for m in messages if m.to_email]
        if not delivered:
            return None

        updates: dict[str, dict[str, object]] = {}
        for message in delivered:
            business = message.business
            business.emailed = True
            record = data_store.outreach_record(message.to_email, message.subject)
            updates[data_store.row_key(business.name)] = {
                "name": business.name,
                "email": message.to_email,
                "contact_name": ", ".join(business.contact_names),
                "scraped_phone": ", ".join(business.phones),
                **record,
            }

        path = data_store.update_listings(self.last_listings_csv, updates)
        if path:
            progress(
                f"💾 Logged {len(delivered)} contact attempt(s) on {path} "
                f"({data_store.STANDARD_EMAIL}); they are now excluded from the call script."
            )
        else:
            progress(
                "⚠ No listings CSV to log outreach against — emails were sent but not recorded."
            )
        return path

    def _sender(self):
        """Build the SMTP sender from the configured account.

        Everything that talks to SMTP goes through here, so a connection test
        and a real campaign cannot end up using different accounts.
        """
        from send_emails import EmailSender

        return EmailSender(
            from_email=self.from_email,
            smtp_server=self.smtp_server,
            smtp_port=self.smtp_port,
            smtp_username=self.smtp_username,
            reply_to=self.reply_to,
        )

    def _safe_export_contacts(
        self, businesses: Sequence[Business], progress: ProgressFn
    ) -> None:
        """Export contacts without letting a disk error mask a scrape error."""
        try:
            self.export_contacts(businesses, progress=progress)
        except OSError as exc:  # pragma: no cover - filesystem dependent
            progress(f"⚠ could not save contacts CSV: {exc}")

    def _finish_search(
        self, businesses: Sequence[Business], field: str, location: str,
        progress: ProgressFn,
    ) -> None:
        """Stamp and save whatever a search collected.

        Called from a ``finally``: a search that is stopped part-way, or that
        dies on a bad page, still files the listings it already opened rather
        than throwing the work away.
        """
        if not businesses:
            return
        self._remember_search(businesses, field, location)
        try:
            self.export_listings(businesses, progress=progress)
        except OSError as exc:  # pragma: no cover - filesystem dependent
            progress(f"⚠ could not save listings CSV: {exc}")

    # -- steps ---------------------------------------------------------------
    def search(
        self,
        field: str,
        location: str = "",
        *,
        max_scrolls: int = 8,
        progress: ProgressFn = _noop,
        on_business: BusinessFn = _noop_business,
    ) -> List[Business]:
        """Search Google Maps.

        ``on_business`` fires as each listing is extracted, so a caller can
        show results while the run is still going — and keep the ones it has
        already been handed if the run is stopped before it finishes.
        """
        raise NotImplementedError

    def scrape_contacts(
        self,
        businesses: Sequence[Business],
        *,
        progress: ProgressFn = _noop,
        on_event: ScanFn = _noop_event,
    ) -> List[Business]:
        raise NotImplementedError

    def find_phones(
        self,
        businesses: Sequence[Business],
        *,
        sources: Sequence[str] = ("google", "yellowpages"),
        progress: ProgressFn = _noop,
        on_event: ScanFn = _noop_event,
    ) -> List[Business]:
        """Look up phone numbers for businesses the website scan drew a blank on."""
        raise NotImplementedError

    def build_message(
        self,
        business: Business,
        *,
        industry_key: Optional[str] = None,
        pricing: Optional[dict] = None,
        hero_image: str = "",
    ) -> EmailMessage:
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
        on_business: BusinessFn = _noop_business,
    ) -> List[Business]:
        from google_maps_scraper import GoogleMapsScraper

        progress(f"Launching browser ({'headless' if self.headless else 'visible'})…")
        scraper = GoogleMapsScraper(headless=self.headless)
        # Filled as listings are opened, and saved in the finally below, so a
        # stop or a crash keeps whatever the run had already collected.
        businesses: List[Business] = []
        try:
            progress(f"Searching Google Maps for “{f'{field} {location}'.strip()}”…")
            # max_scrolls decides how much of the feed is loaded before
            # anything is read, so it has to reach the search itself. Passing
            # it only to _scrape_with_progress left the scraper on its own
            # default of 10, and the "max results" setting silently did
            # nothing to how far the feed was scrolled.
            scraper.search(field, location, max_scrolls=max_scrolls)
            # Reuse the scraper's URL collection + detail extraction, but stream
            # progress so the UI does not appear frozen.
            progress("Collecting business listings…")
            self._scrape_with_progress(
                scraper, max_scrolls, progress, businesses, on_business
            )
            progress(f"Found {len(businesses)} businesses.")
            return list(businesses)
        finally:
            scraper.close()
            self._finish_search(businesses, field, location, progress)

    def _scrape_with_progress(
        self, scraper, max_scrolls, progress, businesses=None,
        on_business: BusinessFn = _noop_business,
    ) -> None:
        """Drive ``scraper.scrape_listings`` while emitting progress lines."""
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By

        collected = businesses if businesses is not None else []
        try:
            scraper.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]'))
            )
        except Exception:
            progress("Results feed did not load in time.")
            return

        # Read the feed's cards before opening anything. Once a place page is
        # open the feed is gone, and the card is the only dependable source of
        # the phone number: the detail panel routinely hydrates only halfway
        # when it is reached by direct URL navigation, and the phone row is
        # among the first things missing.
        #
        # This loop used to skip the harvest and call _extract_business_details
        # with no card at all, which is why the desktop app's Phone column came
        # up empty while `python google_maps_scraper.py` — which goes through
        # scrape_listings — filled it in.
        try:
            scraper._harvest_cards()
        except Exception:  # pragma: no cover - a bare feed is still scrapable
            pass

        urls = scraper._collect_all_business_urls()
        progress(f"Collected {len(urls)} listing links; opening each…")
        for idx, url in enumerate(urls, 1):
            try:
                # _scrape_one retries a half-rendered panel and, if it never
                # hydrates, falls back to the card rather than dropping the
                # business — so a slow listing costs a website, not a name and
                # a phone number.
                data = scraper._scrape_one(url, scraper._cards.get(url, {}))
                if data:
                    scraper.businesses.append(data)
                    business = Business.from_dict(data)
                    collected.append(business)
                    # Hand it over before the next progress line, which is
                    # where a stop request surfaces.
                    on_business(business)
                    progress(f"[{idx}/{len(urls)}] {data.get('name', 'business')}"
                             f" — {data.get('phone') or 'no phone'}")
            except Exception as exc:  # pragma: no cover - network dependent
                progress(f"[{idx}/{len(urls)}] error: {str(exc)[:80]}")

    def scrape_contacts(
        self,
        businesses: Sequence[Business],
        *,
        progress: ProgressFn = _noop,
        on_event: ScanFn = _noop_event,
    ) -> List[Business]:
        from contact_scraper import ContactScraper

        progress("Launching browser for website contact scraping…")
        scraper = ContactScraper(headless=self.headless)
        try:
            total = len(businesses)
            for idx, business in enumerate(businesses, 1):
                label = business.name or "business"
                business.scanned = True

                if not business.website:
                    progress(f"[{idx}/{total}] {label}: no website, skipping")
                    on_event(ScanEvent(idx, total, label, status="skipped"))
                    continue

                progress(f"[{idx}/{total}] {label}: scanning {business.website}")
                on_event(ScanEvent(idx, total, label, website=business.website))

                try:
                    info = scraper.scrape_website(business.website)
                except Exception as exc:  # pragma: no cover - network dependent
                    # One bad site must not abort the whole batch.
                    message = str(exc)[:80]
                    progress(f"    ⚠ error: {message}")
                    on_event(
                        ScanEvent(
                            idx, total, label, website=business.website,
                            status="error", error=message,
                        )
                    )
                    continue

                business.emails = list(info.get("emails", []))
                business.phones = list(info.get("phones", []))
                business.contact_names = list(info.get("contact_names", []))
                business.insights = dict(info.get("insights", {}) or {})
                business.social_links = list(info.get("social_links", []) or [])
                if business.insights:
                    business.insights["contact_info"] = (
                        len(business.emails) + len(business.phones)
                        + len(business.contact_names)
                    )
                if business.emails:
                    progress(f"    ✓ {', '.join(business.emails)}")
                else:
                    progress("    ✗ no email found")
                if business.phones:
                    progress(f"    ☎ {', '.join(business.phones[:3])}")
                on_event(
                    ScanEvent(
                        idx, total, label, website=business.website, status="done",
                        emails=list(business.emails), phones=list(business.phones),
                        contact_names=list(business.contact_names),
                        insights=dict(business.insights),
                        social_links=list(business.social_links),
                    )
                )
                time.sleep(self.scan_delay)
            return list(businesses)
        finally:
            scraper.close()
            # Save whatever was scanned, even if the batch aborted part-way.
            self._safe_export_contacts(businesses, progress)

    def find_phones(
        self,
        businesses: Sequence[Business],
        *,
        sources: Sequence[str] = ("google", "yellowpages"),
        progress: ProgressFn = _noop,
        on_event: ScanFn = _noop_event,
    ) -> List[Business]:
        from phone_lookup import PhoneLookup

        # The businesses the website scan came up empty on — those are the ones
        # a directory search can still rescue.
        targets = [b for b in businesses if not b.has_contact_info]
        if not targets:
            progress("Every business already has contact info.")
            return list(businesses)

        label = " + ".join(sources)
        progress(f"Looking up {len(targets)} phone number(s) on {label}…")
        lookup = PhoneLookup(headless=self.headless)
        try:
            self._run_lookup(lookup, targets, sources, progress, on_event)
            return list(businesses)
        finally:
            lookup.close()
            # The numbers we just found have to reach the CSVs (and through
            # them the call script), even if the batch died half way.
            self._safe_export_contacts(businesses, progress)

    def _run_lookup(self, lookup, targets, sources, progress, on_event) -> None:
        total = len(targets)
        for idx, business in enumerate(targets, 1):
            name = business.name or "business"
            where = business.address or business.search_location
            progress(f"[{idx}/{total}] {name}: searching {' + '.join(sources)}…")
            on_event(ScanEvent(idx, total, name, status="scanning"))

            try:
                result = lookup.find(name, where, sources=tuple(sources))
            except Exception as exc:  # pragma: no cover - network dependent
                message = str(exc)[:80]
                progress(f"    ⚠ error: {message}")
                on_event(ScanEvent(idx, total, name, status="error", error=message))
                continue

            phones = result.get("phones", [])
            if phones:
                business.phones = phones
                business.phone_source = result.get("source", "")
                progress(f"    ☎ {', '.join(phones)}  [via {business.phone_source}]")
                on_event(
                    ScanEvent(idx, total, name, status="done", phones=list(phones))
                )
            else:
                progress("    ✗ no phone number found")
                on_event(ScanEvent(idx, total, name, status="skipped"))
            time.sleep(self.scan_delay)

    def build_message(
        self,
        business: Business,
        *,
        industry_key: Optional[str] = None,
        pricing: Optional[dict] = None,
        hero_image: str = "",
    ) -> EmailMessage:
        from generate_emails import EmailGenerator

        # Per-industry mode: no single template_path, render from templates_dir.
        generator = EmailGenerator(
            output_dir="generated_emails",
            from_email=self.from_email,
            templates_dir=self.templates_dir,
        )
        html, _filename, email = generator.generate_email(
            business.to_generator_row(),
            industry_key=industry_key or (business.industry_key or None),
            pricing=pricing,
            hero_image=hero_image or business.hero_image,
        )
        subject = self._sender().generate_subject_line(
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
        sender = self._sender()
        stats = {"sent": 0, "failed": 0, "skipped": 0, "total": len(messages)}
        delivered: List[EmailMessage] = []

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
                if ok:
                    delivered.append(msg)
                if idx < len(messages):
                    time.sleep(delay)
        finally:
            if not dry_run:
                sender.disconnect()
            # Log even a partial run: whoever was emailed must not be called.
            self.record_outreach(delivered, progress=progress)
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

    # Demo names are built from the search term so two industries produce two
    # distinct sets of businesses, the way a real search would.
    _NAME_TEMPLATES = (
        "{trade} Pros", "Premier {trade}", "{trade} Masters",
        "All-Star {trade}", "Reliable {trade} Co.",
    )

    _GENERIC_WORDS = ("contractors", "contractor", "services", "service",
                      "companies", "company")

    @classmethod
    def _demo_trade(cls, field: str) -> str:
        """Turn a search term into a word that reads well inside a name."""
        words = [w for w in (field or "electricians").split()
                 if w.lower() not in cls._GENERIC_WORDS]
        trade = " ".join(words).title() or "Local"
        if trade.lower().endswith("s") and not trade.lower().endswith("ss"):
            trade = trade[:-1]  # "Plumbers" -> "Plumber"
        return trade

    @classmethod
    def _demo_name(cls, field: str, index: int) -> str:
        trade = cls._demo_trade(field)
        return cls._NAME_TEMPLATES[index % len(cls._NAME_TEMPLATES)].format(trade=trade)

    @staticmethod
    def _demo_slug(name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum()) or "business"

    def search(
        self,
        field: str,
        location: str = "",
        *,
        max_scrolls: int = 8,
        progress: ProgressFn = _noop,
        on_business: BusinessFn = _noop_business,
    ) -> List[Business]:
        progress(f"[demo] pretending to search for “{f'{field} {location}'.strip()}”…")
        businesses: List[Business] = []
        # Honour the cap here rather than trimming afterwards, so the CSV the
        # run exports matches the rows the caller is given.
        sample = self._SAMPLE[: self.max_results] if self.max_results else self._SAMPLE
        try:
            for index, (_sample_name, cat, rating, addr, site, phone, _emails, _names) in enumerate(
                sample
            ):
                time.sleep(0.15)
                name = self._demo_name(field, index)
                slug = self._demo_slug(name)
                b = Business(
                    name=name,
                    category=field.title() if field else cat,
                    rating=rating, address=addr,
                    website=f"https://{slug}.example" if site else "",
                    phone=phone, reviews_count="42",
                    # The index lets the contact scan find this row's canned
                    # data even though the name changes with the search term.
                    url=f"https://maps.google.com/?demo={index}",
                )
                businesses.append(b)
                on_business(b)
                progress(f"  found: {name}")
            progress(f"[demo] found {len(businesses)} businesses.")
            return list(businesses)
        finally:
            # Same contract as the live pipeline: a stopped demo run keeps
            # what it already produced.
            self._finish_search(businesses, field, location, progress)

    def scrape_contacts(
        self,
        businesses: Sequence[Business],
        *,
        progress: ProgressFn = _noop,
        on_event: ScanFn = _noop_event,
    ) -> List[Business]:
        total = len(businesses)
        try:
            return self._demo_scan(businesses, total, progress, on_event)
        finally:
            # Same contract as the live pipeline: a stopped scan still files
            # what it managed to collect.
            self._safe_export_contacts(businesses, progress)

    def _demo_scan(self, businesses, total, progress, on_event):
        for idx, business in enumerate(businesses, 1):
            label = business.name or "business"
            business.scanned = True

            if not business.website:
                progress(f"[{idx}/{total}] {label}: no website, skipping")
                on_event(ScanEvent(idx, total, label, status="skipped"))
                continue

            progress(f"[{idx}/{total}] {label}: scanning {business.website}")
            on_event(ScanEvent(idx, total, label, website=business.website))
            time.sleep(0.2)

            row = self._sample_for(business)
            if row:
                slug = self._demo_slug(business.name)
                # Addresses follow the (renamed) business, so the demo reads as
                # one coherent set rather than a mix of two — same mailbox
                # names as the sample row, re-hosted on this business's domain.
                business.emails = [
                    f"{address.split('@')[0]}@{slug}.example" for address in row[6]
                ]
                business.contact_names = list(row[7])
                business.phones = [row[5]] if row[5] else []
            business.insights = self._demo_insights(business, idx)
            business.social_links = [
                f"https://facebook.com/{business.name.split()[0].lower()}",
                f"https://linkedin.com/company/{business.name.split()[0].lower()}",
            ][: 1 + idx % 2]
            if business.emails:
                progress(f"    ✓ {', '.join(business.emails)}")
            else:
                progress("    ✗ no email found")
            if business.phones:
                progress(f"    ☎ {', '.join(business.phones[:3])}")
            on_event(
                ScanEvent(
                    idx, total, label, website=business.website, status="done",
                    emails=list(business.emails), phones=list(business.phones),
                    contact_names=list(business.contact_names),
                    insights=dict(business.insights),
                    social_links=list(business.social_links),
                )
            )
        return list(businesses)

    def _sample_for(self, business):
        """The canned row behind a demo business, found by its stamped index."""
        match = re.search(r"[?&]demo=(\d+)", business.url or "")
        if match:
            index = int(match.group(1))
            if index < len(self._SAMPLE):
                return self._SAMPLE[index]
        for row in self._SAMPLE:  # a business built by hand still resolves
            if row[0] == business.name:
                return row
        return None

    @staticmethod
    def _demo_insights(business, idx: int) -> dict:
        """Stable, believable category counts for the demo tour."""
        return {
            "business_info": 1,
            "contact_info": len(business.emails) + len(business.phones),
            "services": 4 + idx,
            "about_us": 1,
            "reviews": 8 + idx * 2,
            "social_links": len(business.social_links),
            "images": 9 + idx * 3,
            "team": idx % 4,
            "blog_news": idx % 2,
            "certifications": 1 + idx % 3,
            "hours": 1,
        }

    def find_phones(
        self,
        businesses: Sequence[Business],
        *,
        sources: Sequence[str] = ("google", "yellowpages"),
        progress: ProgressFn = _noop,
        on_event: ScanFn = _noop_event,
    ) -> List[Business]:
        targets = [b for b in businesses if not b.has_contact_info]
        if not targets:
            progress("[demo] every business already has contact info.")
            return list(businesses)

        source = sources[0] if sources else "google"
        progress(f"[demo] looking up {len(targets)} phone number(s) on {' + '.join(sources)}…")
        try:
            return self._demo_lookup(businesses, targets, source, progress, on_event)
        finally:
            self._safe_export_contacts(businesses, progress)

    def _demo_lookup(self, businesses, targets, source, progress, on_event):
        for idx, business in enumerate(targets, 1):
            name = business.name or "business"
            on_event(ScanEvent(idx, len(targets), name, status="scanning"))
            time.sleep(0.2)
            # Deterministic stand-in for a real directory hit.
            phone = f"(614) 555-0{100 + idx:03d}"
            business.phones = [phone]
            business.phone_source = source
            progress(f"[{idx}/{len(targets)}] {name}: ☎ {phone}  [via {source}]")
            on_event(
                ScanEvent(idx, len(targets), name, status="done", phones=[phone])
            )
        return list(businesses)

    def build_message(
        self,
        business: Business,
        *,
        industry_key: Optional[str] = None,
        pricing: Optional[dict] = None,
        hero_image: str = "",
    ) -> EmailMessage:
        subject = f"Transform {business.name}'s Online Presence"
        # Render the real dark industry template so the demo previews exactly what
        # a live run produces. Falls back to plain HTML if a template is missing.
        try:
            from generate_emails import EmailGenerator

            generator = EmailGenerator(
                output_dir="generated_emails",
                from_email=self.from_email,
                templates_dir=self.templates_dir,
            )
            html, _filename, _email = generator.generate_email(
                business.to_generator_row(),
                industry_key=industry_key or (business.industry_key or None),
                pricing=pricing,
                hero_image=hero_image or business.hero_image,
            )
        except OSError:
            location = (
                business.address.split(",")[1].strip()
                if "," in business.address else "your area"
            )
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
        delivered: List[EmailMessage] = []
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
                delivered.append(msg)
        self.record_outreach(delivered, progress=progress)
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
    data_root: Optional[Path] = None,
    templates_dir: str = "email_templates",
) -> Pipeline:
    """Factory returning the appropriate pipeline implementation.

    Demo runs still export their CSVs — but into ``data/_demo/`` so the sample
    rows never mix with real scrapes.
    """
    cls = DemoPipeline if demo else LivePipeline
    # In demo mode the template may not matter, but keep a sane fallback.
    if not demo and not Path(template_path).exists():
        # Fall back gracefully rather than crashing deep in build_message.
        pass
    if data_root is None and demo:
        data_root = data_store.data_root() / "_demo"
    return cls(
        from_email=from_email,
        template_path=template_path,
        headless=headless,
        data_root=data_root,
        templates_dir=templates_dir,
    )
