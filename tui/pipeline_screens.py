"""The five screens of the scrape → contact → email pipeline flow.

Extracted from tui/app.py so the app module holds only OutreachApp. Behavior
is unchanged. Each screen pops back to the screen beneath it on Esc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, OptionList,
    ProgressBar, RichLog, Rule, Select, SelectionList, Static, TextArea,
)
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

import industries
import pricing_store

from .models import Business, EmailMessage, ScanEvent
from .pipeline import Pipeline


@dataclass
class ScanTally:
    """Running totals for the contact scan, shown under the progress bar."""

    total: int = 0
    scanned: int = 0  # businesses finished, whatever the outcome
    with_email: int = 0
    emails: int = 0
    phones: int = 0
    skipped: int = 0  # had no website to visit
    errors: int = 0

    def record(self, event: ScanEvent) -> None:
        """Fold a terminal :class:`ScanEvent` into the totals."""
        self.scanned += 1
        if event.status == "skipped":
            self.skipped += 1
        elif event.status == "error":
            self.errors += 1
        else:
            self.emails += len(event.emails)
            self.phones += len(event.phones)
            if event.emails:
                self.with_email += 1


# --------------------------------------------------------------------------- #
#  Search screen
# --------------------------------------------------------------------------- #
class SearchScreen(Screen):
    """Collect the search field + location and kick off the Maps scrape."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="search-body"):
            yield Static("🔍  [b]Find businesses[/b]", classes="title")
            yield Static(
                "Enter what you want to search for and where. Results appear below "
                "for you to pick from.",
                classes="hint",
            )
            yield Label("What to search for (e.g. electricians)")
            yield Input(placeholder="electricians", id="field")
            yield Label("Location (e.g. Columbus, OH)")
            yield Input(placeholder="Columbus, OH", id="location")
            with Horizontal(id="search-opts"):
                yield Checkbox("Show browser window", value=False, id="visible")
            with Horizontal(id="search-actions"):
                yield Button("Search →", variant="primary", id="go")
            yield Static(
                "[b]enter[/b] run search → results    [b]esc[/b] back    "
                "[dim]every search is saved to data/<term>/<location>/[/dim]",
                classes="keyhints",
            )
            yield Rule()
            yield RichLog(id="search-log", highlight=False, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#field", Input).focus()
        log = self.query_one("#search-log", RichLog)
        if self.app.demo:  # type: ignore[attr-defined]
            log.write("[dim]Demo mode: sample results, no browser needed.[/dim]")

    @on(Input.Submitted, "#field")
    @on(Input.Submitted, "#location")
    def _submit(self) -> None:
        self._start()

    @on(Button.Pressed, "#go")
    def _go(self) -> None:
        self._start()

    def _start(self) -> None:
        field = self.query_one("#field", Input).value.strip()
        if not field:
            self.query_one("#search-log", RichLog).write("[red]Please enter something to search for.[/red]")
            self.query_one("#field", Input).focus()
            return
        location = self.query_one("#location", Input).value.strip()
        visible = self.query_one("#visible", Checkbox).value
        self.app.pipeline.headless = not visible  # type: ignore[attr-defined]
        self.query_one("#go", Button).disabled = True
        log = self.query_one("#search-log", RichLog)
        log.clear()
        self._run_search(field, location)

    def _log(self, msg: str) -> None:
        self.query_one("#search-log", RichLog).write(msg)

    @work(thread=True, exclusive=True)
    def _run_search(self, field: str, location: str) -> None:
        pipeline: Pipeline = self.app.pipeline  # type: ignore[attr-defined]
        progress = lambda m: self.app.call_from_thread(self._log, m)
        try:
            businesses = pipeline.search(field, location, progress=progress)
        except Exception as exc:  # pragma: no cover - runtime/browser dependent
            self.app.call_from_thread(self._log, f"[red]Error: {exc}[/red]")
            self.app.call_from_thread(self._reenable)
            return
        self.app.call_from_thread(self._done, businesses)

    def _reenable(self) -> None:
        self.query_one("#go", Button).disabled = False

    def _done(self, businesses: List[Business]) -> None:
        self._reenable()
        if not businesses:
            self._log("[yellow]No businesses found. Try a different search.[/yellow]")
            return
        self.app.businesses = businesses  # type: ignore[attr-defined]
        self.app.push_screen(ResultsScreen())


# --------------------------------------------------------------------------- #
#  Results screen – choose which businesses to scan
# --------------------------------------------------------------------------- #
class ResultsScreen(Screen):
    """Multi-select list of search results; advances to contact scraping."""

    BINDINGS = [
        Binding("s", "scan", "s  Scan selected → contacts"),
        Binding("e", "skip_to_email", "e  Skip scan → email"),
        Binding("a", "select_all", "Select all"),
        Binding("n", "select_none", "Clear"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._tally = ScanTally()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="results-body"):
            yield Static("✅  [b]Select businesses to scan[/b]", classes="title")
            yield Static(
                "Space toggles a row · [b]a[/b] all · [b]n[/b] none. Selected sites "
                "will be scanned for contact info. Use the button below to continue.",
                classes="hint",
            )
            with Horizontal(id="results-actions"):
                yield Button("← Back", id="back")
                scan = Button("Continue: scan selected websites →", variant="primary", id="scan")
                scan.tooltip = "Scan the selected businesses, then continue to contact selection"
                yield scan
                email = Button("Skip scan: email selected →", id="skip-email")
                email.tooltip = "Go straight to composing emails with the contacts you already have"
                yield email
            yield SelectionList(id="results-list")
            yield Static(
                "[b]s[/b] scan selected → contacts    "
                "[b]e[/b] skip scan → compose emails    "
                "[b]a[/b] select all    [b]n[/b] clear    [b]esc[/b] back",
                classes="keyhints",
            )
            with Vertical(id="scan-panel"):
                with Horizontal(id="scan-bar-row"):
                    yield ProgressBar(id="scan-progress", show_eta=True)
                    yield Static("", id="scan-count", classes="scan-count")
                yield Static("", id="scan-current", classes="hint")
                yield Static("", id="scan-stats")
                yield RichLog(id="results-log", highlight=False, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        businesses: List[Business] = self.app.businesses  # type: ignore[attr-defined]
        sel = self.query_one("#results-list", SelectionList)
        sel.clear_options()
        for idx, b in enumerate(businesses):
            sel.add_option(Selection(b.display_line, idx, True))
        sel.focus()
        self.query_one("#scan-panel", Vertical).border_title = "Website scan"
        self._render_stats()
        log = self.query_one("#results-log", RichLog)
        log.write(f"[dim]{len(businesses)} businesses found. All selected by default.[/dim]")
        saved = getattr(self.app.pipeline, "last_listings_csv", None)  # type: ignore[attr-defined]
        if saved:
            log.write(f"[dim]💾 Listings exported to {saved}[/dim]")

    def action_select_all(self) -> None:
        self.query_one("#results-list", SelectionList).select_all()

    def action_select_none(self) -> None:
        self.query_one("#results-list", SelectionList).deselect_all()

    def action_scan(self) -> None:
        self._scan()

    def action_skip_to_email(self) -> None:
        self._skip_to_email()

    def _selected(self) -> List[Business]:
        businesses: List[Business] = self.app.businesses  # type: ignore[attr-defined]
        chosen_idx = self.query_one("#results-list", SelectionList).selected
        return [businesses[i] for i in chosen_idx]

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#skip-email")
    def _skip_to_email(self) -> None:
        """Take the selection straight to the contact/compose step, unscanned."""
        chosen = self._selected()
        if not chosen:
            self.query_one("#results-log", RichLog).write(
                "[yellow]Select at least one business.[/yellow]"
            )
            return
        self.app.chosen = chosen  # type: ignore[attr-defined]
        self.app.contacts = chosen  # type: ignore[attr-defined]
        self.app.push_screen(ContactsScreen())

    @on(Button.Pressed, "#scan")
    def _scan(self) -> None:
        chosen = self._selected()
        if not chosen:
            self.query_one("#results-log", RichLog).write("[yellow]Select at least one business.[/yellow]")
            return
        self.app.chosen = chosen  # type: ignore[attr-defined]
        self.query_one("#scan", Button).disabled = True
        self.query_one("#back", Button).disabled = True

        self._tally = ScanTally(total=len(chosen))
        bar = self.query_one("#scan-progress", ProgressBar)
        bar.update(total=len(chosen), progress=0)
        self._render_stats()
        self.query_one("#scan-current", Static).update("[dim]Starting browser…[/dim]")

        log = self.query_one("#results-log", RichLog)
        log.clear()
        log.write(f"[b]Scanning {len(chosen)} website(s) for emails and phone numbers…[/b]")
        self._run_scan(chosen)

    def _log(self, msg: str) -> None:
        self.query_one("#results-log", RichLog).write(msg)

    def _render_stats(self) -> None:
        """Repaint the counters line and the "x of y" label beside the bar."""
        t = self._tally
        self.query_one("#scan-count", Static).update(
            f"[b]{t.scanned}[/b]/{t.total}" if t.total else ""
        )
        self.query_one("#scan-stats", Static).update(
            f"[green]✉ {t.emails} email(s)[/green]   "
            f"[cyan]☎ {t.phones} phone(s)[/cyan]   "
            f"[b]{t.with_email}[/b] site(s) with an email   "
            f"[dim]{t.skipped} no website · {t.errors} error(s)[/dim]"
        )

    def _on_event(self, event: ScanEvent) -> None:
        """Apply one pipeline scan event to the bar, counters and current line."""
        current = self.query_one("#scan-current", Static)
        if not event.finished:
            current.update(
                f"[b]{event.index}/{event.total}[/b]  scanning "
                f"[b]{event.name}[/b] [dim]{event.website}[/dim]"
            )
            return

        self._tally.record(event)
        self.query_one("#scan-progress", ProgressBar).advance(1)
        self._render_stats()
        if self._tally.scanned >= self._tally.total:
            current.update("[dim]Scan complete.[/dim]")

    @work(thread=True, exclusive=True)
    def _run_scan(self, chosen: List[Business]) -> None:
        pipeline: Pipeline = self.app.pipeline  # type: ignore[attr-defined]
        progress = lambda m: self.app.call_from_thread(self._log, m)
        on_event = lambda e: self.app.call_from_thread(self._on_event, e)
        try:
            pipeline.scrape_contacts(chosen, progress=progress, on_event=on_event)
        except Exception as exc:  # pragma: no cover - runtime/browser dependent
            self.app.call_from_thread(self._log, f"[red]Error: {exc}[/red]")
            self.app.call_from_thread(self._fail, str(exc))
            return
        self.app.call_from_thread(self._done, chosen)

    def _reenable(self) -> None:
        self.query_one("#scan", Button).disabled = False
        self.query_one("#back", Button).disabled = False

    def _fail(self, message: str) -> None:
        self._reenable()
        self.query_one("#scan-current", Static).update(f"[red]Scan aborted: {message}[/red]")

    def _done(self, chosen: List[Business]) -> None:
        self._reenable()
        t = self._tally
        self._log(
            f"[b green]Scan complete[/b green] — {t.scanned} site(s) scanned, "
            f"{t.emails} email(s) and {t.phones} phone(s) found."
        )
        self.app.contacts = chosen  # type: ignore[attr-defined]
        self.app.push_screen(ContactsScreen())


# --------------------------------------------------------------------------- #
#  Contacts screen – choose which scraped contacts to email
# --------------------------------------------------------------------------- #
class ContactsScreen(Screen):
    """Show scraped contact info; pick who to build emails for."""

    BINDINGS = [
        Binding("c", "compose", "c  Compose emails →"),
        Binding("g", "lookup_google", "g  Find phones (Google)"),
        Binding("y", "lookup_yellowpages", "y  Find phones (Yellow Pages)"),
        Binding("a", "select_all", "Select all"),
        Binding("n", "select_none", "Clear"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="contacts-body"):
            yield Static("📇  [b]Contacts found[/b]", classes="title")
            yield Static(
                "Businesses with an email are pre-selected. Space toggles a row. "
                "Came up empty? Look the phone number up on Google or Yellow Pages. "
                "Advance to compose personalized emails.",
                classes="hint",
            )
            yield SelectionList(id="contacts-list")
            yield Static(
                "[b]c[/b] compose emails →    [b]g[/b] find phones (Google)    "
                "[b]y[/b] find phones (Yellow Pages)    [b]a[/b] select all    "
                "[b]n[/b] clear    [b]esc[/b] back",
                classes="keyhints",
            )
            with Horizontal(id="contacts-actions"):
                yield Button("← Back", id="back")
                yield Button("☎ Google", id="lookup-google")
                yield Button("☎ Yellow Pages", id="lookup-yp")
                yield Button("Compose emails →", variant="primary", id="compose")
            yield Static("", id="contacts-summary", classes="hint")
            yield RichLog(id="contacts-log", highlight=False, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._populate()

    def _populate(self) -> None:
        """(Re)build the list — also called after a phone lookup fills rows in."""
        contacts: List[Business] = self.app.contacts  # type: ignore[attr-defined]
        sel = self.query_one("#contacts-list", SelectionList)
        sel.clear_options()
        with_email = 0
        already = 0
        for idx, b in enumerate(contacts):
            has = b.has_email
            with_email += 1 if has else 0
            prompt = f"{b.name or '(unnamed)'} — {b.contact_line}"
            if b.emailed:
                # Already contacted: logged on the listings CSV, dropped from
                # the call script, and not re-selected here.
                already += 1
                prompt += "   ✉ already emailed"
            sel.add_option(Selection(prompt, idx, has and not b.emailed))
        sel.focus()

        empty = sum(1 for b in contacts if not b.has_contact_info)
        summary = f"{with_email} of {len(contacts)} businesses have a usable email address."
        if empty:
            summary += (
                f"  {empty} website(s) gave us nothing — press [b]g[/b] (Google) or "
                "[b]y[/b] (Yellow Pages) to look their phone number up."
            )
        if already:
            summary += f"  {already} already emailed (deselected)."
        self.query_one("#contacts-summary", Static).update(summary)

    def action_select_all(self) -> None:
        self.query_one("#contacts-list", SelectionList).select_all()

    def action_select_none(self) -> None:
        self.query_one("#contacts-list", SelectionList).deselect_all()

    def action_compose(self) -> None:
        self._go_compose()

    def action_lookup_google(self) -> None:
        self._lookup(("google",))

    def action_lookup_yellowpages(self) -> None:
        self._lookup(("yellowpages",))

    # -- phone lookup --------------------------------------------------------
    def _log(self, msg: str) -> None:
        self.query_one("#contacts-log", RichLog).write(msg)

    @on(Button.Pressed, "#lookup-google")
    def _lookup_google_button(self) -> None:
        self._lookup(("google",))

    @on(Button.Pressed, "#lookup-yp")
    def _lookup_yp_button(self) -> None:
        self._lookup(("yellowpages",))

    def _lookup(self, sources: tuple[str, ...]) -> None:
        """Search a directory for the businesses whose website told us nothing."""
        contacts: List[Business] = self.app.contacts  # type: ignore[attr-defined]
        empty = [b for b in contacts if not b.has_contact_info]
        log = self.query_one("#contacts-log", RichLog)
        if not empty:
            log.write("[dim]Every business already has contact info.[/dim]")
            return
        for button in ("#lookup-google", "#lookup-yp", "#compose", "#back"):
            self.query_one(button, Button).disabled = True
        log.write(
            f"[b]Searching {', '.join(sources)} for {len(empty)} missing phone number(s)…[/b]"
        )
        self._run_lookup(contacts, sources)

    @work(thread=True, exclusive=True)
    def _run_lookup(self, contacts: List[Business], sources: tuple[str, ...]) -> None:
        pipeline: Pipeline = self.app.pipeline  # type: ignore[attr-defined]
        progress = lambda m: self.app.call_from_thread(self._log, m)
        try:
            pipeline.find_phones(contacts, sources=sources, progress=progress)
        except Exception as exc:  # pragma: no cover - runtime/browser dependent
            self.app.call_from_thread(self._log, f"[red]Lookup failed: {exc}[/red]")
        self.app.call_from_thread(self._lookup_done)

    def _lookup_done(self) -> None:
        for button in ("#lookup-google", "#lookup-yp", "#compose", "#back"):
            self.query_one(button, Button).disabled = False
        self._populate()
        found = sum(1 for b in self.app.contacts if b.phone_source)  # type: ignore[attr-defined]
        saved = getattr(self.app.pipeline, "last_contacts_csv", None)  # type: ignore[attr-defined]
        self._log(
            f"[b green]Lookup complete[/b green] — {found} number(s) from a directory search; "
            "they are in the CSV export and the call script."
        )
        if saved:
            self._log(f"[dim]💾 Contacts exported to {saved}[/dim]")

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#compose")
    def _go_compose(self) -> None:
        contacts: List[Business] = self.app.contacts  # type: ignore[attr-defined]
        chosen_idx = self.query_one("#contacts-list", SelectionList).selected
        recipients = [contacts[i] for i in chosen_idx if contacts[i].has_email]
        summary = self.query_one("#contacts-summary", Static)
        if not recipients:
            summary.update("[yellow]Select at least one business that has an email address.[/yellow]")
            return
        # Pick industry template + pricing on the Customize screen; it builds the
        # messages and advances to Compose.
        self.app.recipients = recipients  # type: ignore[attr-defined]
        self.app.push_screen(CustomizeScreen())


# --------------------------------------------------------------------------- #
#  Pricing defaults modal – edit the persisted per-industry price table
# --------------------------------------------------------------------------- #
class PricingDefaultsModal(ModalScreen):
    """Edit the per-industry default prices and persist them to pricing.json.

    These are the starting prices every business in an industry inherits. A
    business's per-recipient tweaks (on the Customize screen) override them.
    Dismisses ``True`` when prices were saved, ``False`` on cancel.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Working copies of the whole table + hero URLs; saved together on Save.
        self._table = pricing_store.load_pricing()
        self._heroes = pricing_store.load_heroes()
        self._industry = industries.REGISTRY[0].key

    def compose(self) -> ComposeResult:
        with Vertical(id="pricing-modal"):
            yield Static("💲  [b]Default prices per industry[/b]", classes="title")
            yield Static(
                "Pick an industry, edit its package prices, Save. Stored in "
                "pricing.json — no config file to touch.",
                classes="hint",
            )
            yield Label("Industry")
            yield Select(
                industries.choices(), value=self._industry,
                allow_blank=False, id="pd-industry",
            )
            with VerticalScroll(id="pd-fields"):
                for fkey in pricing_store.PACKAGE_FIELDS:
                    yield Label(pricing_store.FIELD_LABELS[fkey])
                    yield Input(id=f"pd-{fkey}")
                yield Label("Hero image URL (optional)")
                yield Input(placeholder="https://…  self-host & paste later", id="pd-hero")
            with Horizontal(id="pd-actions"):
                yield Button("Cancel", id="pd-cancel")
                yield Button("Save", variant="success", id="pd-save")

    def on_mount(self) -> None:
        self._load_fields(self._industry)

    def _load_fields(self, industry_key: str) -> None:
        row = pricing_store.prices_for(industry_key, store=self._table)
        for fkey in pricing_store.PACKAGE_FIELDS:
            self.query_one(f"#pd-{fkey}", Input).value = row.get(fkey, "")
        self.query_one("#pd-hero", Input).value = self._heroes.get(industry_key, "")

    def _stash_fields(self, industry_key: str) -> None:
        row = dict(self._table.get(industry_key, {}))
        for fkey in pricing_store.PACKAGE_FIELDS:
            row[fkey] = self.query_one(f"#pd-{fkey}", Input).value.strip()
        self._table[industry_key] = row
        hero = self.query_one("#pd-hero", Input).value.strip()
        if hero:
            self._heroes[industry_key] = hero
        else:
            self._heroes.pop(industry_key, None)

    @on(Select.Changed, "#pd-industry")
    def _switch_industry(self, event: Select.Changed) -> None:
        if event.value == self._industry:
            return
        self._stash_fields(self._industry)  # keep edits to the one we're leaving
        self._industry = str(event.value)
        self._load_fields(self._industry)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_save(self) -> None:
        self._save()

    @on(Button.Pressed, "#pd-cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#pd-save")
    def _save(self) -> None:
        self._stash_fields(self._industry)
        pricing_store.save_pricing(self._table, heroes=self._heroes)
        self.dismiss(True)


# --------------------------------------------------------------------------- #
#  Customize screen – pick industry template + prices before composing
# --------------------------------------------------------------------------- #
class CustomizeScreen(Screen):
    """Per-recipient industry template + package pricing, before Compose.

    Each recipient gets an auto-detected industry (overridable via a dropdown),
    editable prices (seeded from that industry's saved defaults, overlaid by any
    per-business edits) and an optional hero-image URL. Advancing renders every
    email from these choices and moves on to Compose for final wording tweaks.
    """

    BINDINGS = [
        Binding("ctrl+s", "compose", "^s  Compose emails →"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current = 0
        self._current_industry = industries.GENERAL_KEY
        self._ready = False
        self._loading = False
        # Saved per-industry defaults, reloaded whenever the modal writes them.
        self._store = pricing_store.load_pricing()
        self._heroes = pricing_store.load_heroes()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="customize-body"):
            yield Static("🎛️  [b]Customize & price[/b]", classes="title")
            yield Static(
                "Pick each business's industry template and set its prices. "
                "Prices start from the saved industry defaults; edit them here to "
                "tailor a single business. These drive how each email renders.",
                classes="hint",
            )
            with Horizontal(id="customize-main"):
                yield OptionList(id="customize-recipients")
                with VerticalScroll(id="customize-editor"):
                    yield Label("Industry template")
                    yield Select(
                        industries.choices(), allow_blank=False,
                        value=industries.GENERAL_KEY, id="industry",
                    )
                    yield Label("Hero image URL (optional — blank uses the industry default)")
                    yield Input(placeholder="https://…  override this one business", id="hero-image")
                    yield Static(
                        "[b]Package prices for this business[/b]", classes="hint",
                    )
                    for fkey in pricing_store.PACKAGE_FIELDS:
                        yield Label(pricing_store.FIELD_LABELS[fkey])
                        yield Input(id=f"price-{fkey}")
            yield Static(
                "[b]ctrl+s[/b] compose emails →    [b]esc[/b] back to contacts    "
                "[dim]changing prices here overrides this business only[/dim]",
                classes="keyhints",
            )
            with Horizontal(id="customize-actions"):
                yield Button("← Back", id="back")
                yield Button("Edit industry defaults…", id="defaults")
                yield Button("Compose emails →", variant="primary", id="compose")
        yield Footer()

    def action_compose(self) -> None:
        self._go_compose()

    def on_mount(self) -> None:
        recipients: List[Business] = self.app.recipients  # type: ignore[attr-defined]
        ol = self.query_one("#customize-recipients", OptionList)
        ol.clear_options()
        for b in recipients:
            ind = industries.get(b.industry_key or industries.classify(b.category, b.name))
            ol.add_option(Option(f"{b.name or '(unnamed)'}  ·  {ind.label}"))
        self._current = 0
        self._load(0)
        self._ready = True
        ol.focus()
        if recipients:
            ol.highlighted = 0

    # -- state -------------------------------------------------------------- #
    def _defaults_for(self, industry_key: str) -> dict:
        return pricing_store.prices_for(industry_key, store=self._store)

    def _load(self, index: int) -> None:
        recipients: List[Business] = self.app.recipients  # type: ignore[attr-defined]
        if not (0 <= index < len(recipients)):
            return
        self._loading = True
        b = recipients[index]
        ind = b.industry_key or industries.classify(b.category, b.name)
        self._current_industry = ind
        self.query_one("#industry", Select).value = ind
        self.query_one("#hero-image", Input).value = b.hero_image
        merged = {**self._defaults_for(ind), **b.price_overrides}
        for fkey in pricing_store.PACKAGE_FIELDS:
            self.query_one(f"#price-{fkey}", Input).value = merged.get(fkey, "")
        self._loading = False

    def _save(self, index: int) -> None:
        recipients: List[Business] = self.app.recipients  # type: ignore[attr-defined]
        if not (0 <= index < len(recipients)):
            return
        b = recipients[index]
        ind = self._current_industry
        b.industry_key = ind
        b.hero_image = self.query_one("#hero-image", Input).value.strip()
        defaults = self._defaults_for(ind)
        overrides = {}
        for fkey in pricing_store.PACKAGE_FIELDS:
            val = self.query_one(f"#price-{fkey}", Input).value.strip()
            if val and val != defaults.get(fkey):
                overrides[fkey] = val
        b.price_overrides = overrides

    def _refresh_recipient_label(self, index: int) -> None:
        recipients: List[Business] = self.app.recipients  # type: ignore[attr-defined]
        b = recipients[index]
        ind = industries.get(b.industry_key or industries.classify(b.category, b.name))
        ol = self.query_one("#customize-recipients", OptionList)
        # OptionList has no in-place edit; rebuild the single changed label cheaply.
        options = [
            Option(
                f"{rb.name or '(unnamed)'}  ·  "
                f"{industries.get(rb.industry_key or industries.classify(rb.category, rb.name)).label}"
            )
            for rb in recipients
        ]
        highlighted = ol.highlighted
        ol.clear_options()
        for opt in options:
            ol.add_option(opt)
        ol.highlighted = highlighted

    @on(OptionList.OptionHighlighted, "#customize-recipients")
    def _switch(self, event: OptionList.OptionHighlighted) -> None:
        if not self._ready or event.option_index is None:
            return
        if event.option_index == self._current:
            return
        self._save(self._current)
        self._current = event.option_index
        self._load(self._current)

    @on(Select.Changed, "#industry")
    def _industry_changed(self, event: Select.Changed) -> None:
        if self._loading or not self._ready:
            return
        new_ind = str(event.value)
        if new_ind == self._current_industry:
            return
        recipients: List[Business] = self.app.recipients  # type: ignore[attr-defined]
        b = recipients[self._current]
        # Preserve deliberate per-business price edits across an industry switch,
        # then repopulate the inputs from the new industry's defaults.
        old_defaults = self._defaults_for(self._current_industry)
        overrides = {}
        for fkey in pricing_store.PACKAGE_FIELDS:
            val = self.query_one(f"#price-{fkey}", Input).value.strip()
            if val and val != old_defaults.get(fkey):
                overrides[fkey] = val
        b.price_overrides = overrides
        b.industry_key = new_ind
        self._current_industry = new_ind
        merged = {**self._defaults_for(new_ind), **overrides}
        for fkey in pricing_store.PACKAGE_FIELDS:
            self.query_one(f"#price-{fkey}", Input).value = merged.get(fkey, "")
        self._refresh_recipient_label(self._current)

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self._save(self._current)
        self.app.pop_screen()

    @on(Button.Pressed, "#defaults")
    def _edit_defaults(self) -> None:
        self._save(self._current)
        self.app.push_screen(PricingDefaultsModal(), self._defaults_saved)

    def _defaults_saved(self, saved: bool) -> None:
        if not saved:
            return
        # Reload the persisted table and re-render the current recipient's inputs
        # so any non-overridden prices reflect the new defaults.
        self._store = pricing_store.load_pricing()
        self._heroes = pricing_store.load_heroes()
        self._load(self._current)

    @on(Button.Pressed, "#compose")
    def _go_compose(self) -> None:
        self._save(self._current)
        recipients: List[Business] = self.app.recipients  # type: ignore[attr-defined]
        pipeline: Pipeline = self.app.pipeline  # type: ignore[attr-defined]
        messages: List[EmailMessage] = []
        for b in recipients:
            prices = {**self._defaults_for(b.industry_key), **b.price_overrides}
            # Per-business hero wins; otherwise the industry's saved hero URL.
            hero = b.hero_image or pricing_store.hero_for(b.industry_key, self._heroes)
            try:
                messages.append(
                    pipeline.build_message(
                        b, industry_key=b.industry_key or None,
                        pricing=prices, hero_image=hero,
                    )
                )
            except Exception as exc:  # pragma: no cover - runtime dependent
                self.query_one("#customize-body", Vertical).mount(
                    Static(f"[red]Failed to build email for {b.name}: {exc}[/red]")
                )
                return
        self.app.messages = messages  # type: ignore[attr-defined]
        self.app.push_screen(ComposeScreen())


# --------------------------------------------------------------------------- #
#  Compose screen – edit each email before sending
# --------------------------------------------------------------------------- #
class ComposeScreen(Screen):
    """Per-recipient editable subject + HTML body."""

    # Letter keys would be swallowed by the subject / body editors, so the
    # advance key is a chord here.
    BINDINGS = [
        Binding("ctrl+s", "send", "^s  Send emails →"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current = 0
        self._ready = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="compose-body"):
            yield Static("✉️  [b]Compose & customize[/b]", classes="title")
            yield Static(
                "Pick a recipient on the left, edit the subject and message on the "
                "right. Edits are kept as you switch between recipients.",
                classes="hint",
            )
            with Horizontal(id="compose-main"):
                yield OptionList(id="recipient-list")
                with Vertical(id="editor"):
                    yield Label("To")
                    yield Static("", id="to-field", classes="readonly")
                    yield Label("Subject")
                    yield Input(id="subject-field")
                    yield Label("Message (HTML)")
                    yield TextArea(id="body-field")
            yield Static(
                "[b]ctrl+s[/b] send emails →    [b]esc[/b] back to contacts",
                classes="keyhints",
            )
            with Horizontal(id="compose-actions"):
                yield Button("← Back", id="back")
                yield Button("Send emails →", variant="primary", id="send")
        yield Footer()

    def action_send(self) -> None:
        self._go_send()

    def on_mount(self) -> None:
        messages: List[EmailMessage] = self.app.messages  # type: ignore[attr-defined]
        ol = self.query_one("#recipient-list", OptionList)
        ol.clear_options()
        for m in messages:
            ol.add_option(Option(m.label))
        self._current = 0
        self._load(0)
        self._ready = True
        ol.focus()
        if messages:
            ol.highlighted = 0

    def _load(self, index: int) -> None:
        messages: List[EmailMessage] = self.app.messages  # type: ignore[attr-defined]
        if not (0 <= index < len(messages)):
            return
        m = messages[index]
        self.query_one("#to-field", Static).update(m.to_email or "[red]no address[/red]")
        self.query_one("#subject-field", Input).value = m.subject
        self.query_one("#body-field", TextArea).text = m.html

    def _save(self, index: int) -> None:
        messages: List[EmailMessage] = self.app.messages  # type: ignore[attr-defined]
        if not (0 <= index < len(messages)):
            return
        m = messages[index]
        m.subject = self.query_one("#subject-field", Input).value
        m.html = self.query_one("#body-field", TextArea).text

    @on(OptionList.OptionHighlighted, "#recipient-list")
    def _switch(self, event: OptionList.OptionHighlighted) -> None:
        if not self._ready or event.option_index is None:
            return
        if event.option_index == self._current:
            return
        self._save(self._current)
        self._current = event.option_index
        self._load(self._current)

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self._save(self._current)
        self.app.pop_screen()

    @on(Button.Pressed, "#send")
    def _go_send(self) -> None:
        self._save(self._current)
        self.app.push_screen(SendScreen())


# --------------------------------------------------------------------------- #
#  Send screen – SMTP credentials + delivery log
# --------------------------------------------------------------------------- #
class SendScreen(Screen):
    """Collect the SMTP password and send (or dry-run) all composed emails."""

    BINDINGS = [
        Binding("ctrl+s", "send_now", "^s  Send"),
        Binding("ctrl+f", "finish", "^f  Finish →"),
        Binding("escape", "app.pop_screen", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="send-body"):
            yield Static("🚀  [b]Send emails[/b]", classes="title")
            yield Static("", id="send-info", classes="hint")
            with Horizontal(id="send-opts"):
                yield Checkbox("Dry run (don't actually send)", value=True, id="dry")
                yield Label("Delay (s)")
                yield Input(value="2", id="delay", classes="tiny")
            yield Label("Email password / app password", id="pw-label")
            yield Input(password=True, id="password", placeholder="app password")
            with Horizontal(id="send-actions"):
                yield Button("← Back", id="back")
                yield Button("Send", variant="success", id="do-send")
                yield Button("Finish workflow →", variant="primary", id="finish", disabled=True)
            yield Static(
                "[b]ctrl+s[/b] send    [b]ctrl+f[/b] finish →    [b]esc[/b] back to compose",
                classes="keyhints",
            )
            yield Rule()
            yield RichLog(id="send-log", highlight=False, markup=True, wrap=True)
        yield Footer()

    def action_send_now(self) -> None:
        self._do_send()

    def action_finish(self) -> None:
        if not self.query_one("#finish", Button).disabled:
            self._complete()

    def on_mount(self) -> None:
        messages: List[EmailMessage] = self.app.messages  # type: ignore[attr-defined]
        from_email = self.app.pipeline.from_email  # type: ignore[attr-defined]
        self.query_one("#send-info", Static).update(
            f"Sending {len(messages)} email(s) from [b]{from_email}[/b]. "
            "Leave [b]Dry run[/b] on for a safe preview first."
        )
        if self.app.demo:  # type: ignore[attr-defined]
            self.query_one("#send-log", RichLog).write(
                "[dim]Demo mode: nothing is really sent; no password needed.[/dim]"
            )

    def _log(self, msg: str) -> None:
        self.query_one("#send-log", RichLog).write(msg)

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#do-send")
    def _do_send(self) -> None:
        dry = self.query_one("#dry", Checkbox).value
        password = self.query_one("#password", Input).value
        try:
            delay = float(self.query_one("#delay", Input).value or "2")
        except ValueError:
            delay = 2.0
        if not dry and not password and not self.app.demo:  # type: ignore[attr-defined]
            self._log("[yellow]Enter your email password, or keep Dry run enabled.[/yellow]")
            return
        self.query_one("#do-send", Button).disabled = True
        self.query_one("#back", Button).disabled = True
        self.query_one("#send-log", RichLog).clear()
        messages: List[EmailMessage] = self.app.messages  # type: ignore[attr-defined]
        self._run_send(messages, password, delay, dry)

    @work(thread=True, exclusive=True)
    def _run_send(self, messages, password, delay, dry) -> None:
        pipeline: Pipeline = self.app.pipeline  # type: ignore[attr-defined]
        progress = lambda m: self.app.call_from_thread(self._log, m)
        try:
            stats = pipeline.send(
                messages, password=password, delay=delay, dry_run=dry, progress=progress
            )
        except Exception as exc:  # pragma: no cover - runtime dependent
            self.app.call_from_thread(self._log, f"[red]Error: {exc}[/red]")
            self.app.call_from_thread(self._reenable)
            return
        self.app.call_from_thread(self._finish, stats)

    def _reenable(self) -> None:
        self.query_one("#do-send", Button).disabled = False
        self.query_one("#back", Button).disabled = False

    def _finish(self, stats: dict) -> None:
        self._reenable()
        self._stats = stats
        self._log(
            f"[b green]Finished[/b green] — sent {stats.get('sent', 0)}, "
            f"failed {stats.get('failed', 0)}, skipped {stats.get('skipped', 0)}."
        )
        self.query_one("#finish", Button).disabled = False

    @on(Button.Pressed, "#finish")
    def _complete(self) -> None:
        self.app.push_screen(CompleteScreen(getattr(self, "_stats", {})))


class CompleteScreen(Screen):
    """Final workflow summary with a direct path into another campaign."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self, stats: dict) -> None:
        super().__init__()
        self.stats = stats

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="complete-body"):
            yield Static("✅  [b]Outreach workflow complete[/b]", classes="title")
            yield Static(
                "Results scraped → websites scanned → contacts gathered → "
                "emails assembled → delivery completed.",
                classes="hint",
            )
            yield Static("", id="complete-summary")
            yield Static("", id="complete-exports", classes="hint")
            with Horizontal(id="complete-actions"):
                yield Button("Start another campaign", variant="primary", id="restart")
                yield Button("Return home", id="home")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#complete-summary", Static).update(
            f"Businesses: [b]{len(self.app.businesses)}[/b]   "  # type: ignore[attr-defined]
            f"Websites scanned: [b]{len(self.app.contacts)}[/b]   "  # type: ignore[attr-defined]
            f"Emails assembled: [b]{len(self.app.messages)}[/b]   "  # type: ignore[attr-defined]
            f"Sent: [b green]{self.stats.get('sent', 0)}[/b green]   "
            f"Failed: [b red]{self.stats.get('failed', 0)}[/b red]   "
            f"Skipped: [b]{self.stats.get('skipped', 0)}[/b]"
        )

        pipeline = self.app.pipeline  # type: ignore[attr-defined]
        lines = []
        if getattr(pipeline, "last_listings_csv", None):
            lines.append(f"💾 Listings + outreach log: {pipeline.last_listings_csv}")
        if getattr(pipeline, "last_contacts_csv", None):
            lines.append(f"💾 Contacts: {pipeline.last_contacts_csv}")
        emailed = sum(1 for b in self.app.contacts if b.emailed)  # type: ignore[attr-defined]
        if emailed:
            lines.append(
                f"{emailed} business(es) logged as emailed — they are excluded from the call script."
            )
        self.query_one("#complete-exports", Static).update("\n".join(lines))

    @on(Button.Pressed, "#restart")
    def _restart(self) -> None:
        self.app.reset_pipeline_state()  # type: ignore[attr-defined]
        self.app.push_screen(SearchScreen())

    @on(Button.Pressed, "#home")
    def _home(self) -> None:
        from .home import HomeScreen
        self.app.push_screen(HomeScreen())
