"""The five screens of the scrape → contact → email pipeline flow.

Extracted from tui/app.py so the app module holds only OutreachApp. Behavior
is unchanged. Each screen pops back to the screen beneath it on Esc.
"""

from __future__ import annotations

from typing import List

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, OptionList,
    RichLog, Rule, SelectionList, Static, TextArea,
)
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from .models import Business, EmailMessage
from .pipeline import Pipeline


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
        Binding("escape", "app.pop_screen", "Back"),
        Binding("a", "select_all", "Select all"),
        Binding("n", "select_none", "Clear"),
    ]

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
            yield SelectionList(id="results-list")
            yield Rule()
            yield RichLog(id="results-log", highlight=False, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        businesses: List[Business] = self.app.businesses  # type: ignore[attr-defined]
        sel = self.query_one("#results-list", SelectionList)
        sel.clear_options()
        for idx, b in enumerate(businesses):
            sel.add_option(Selection(b.display_line, idx, True))
        sel.focus()
        self.query_one("#results-log", RichLog).write(
            f"[dim]{len(businesses)} businesses found. All selected by default.[/dim]"
        )

    def action_select_all(self) -> None:
        self.query_one("#results-list", SelectionList).select_all()

    def action_select_none(self) -> None:
        self.query_one("#results-list", SelectionList).deselect_all()

    @on(Button.Pressed, "#back")
    def _back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#scan")
    def _scan(self) -> None:
        businesses: List[Business] = self.app.businesses  # type: ignore[attr-defined]
        chosen_idx = self.query_one("#results-list", SelectionList).selected
        chosen = [businesses[i] for i in chosen_idx]
        if not chosen:
            self.query_one("#results-log", RichLog).write("[yellow]Select at least one business.[/yellow]")
            return
        self.app.chosen = chosen  # type: ignore[attr-defined]
        self.query_one("#scan", Button).disabled = True
        self.query_one("#back", Button).disabled = True
        log = self.query_one("#results-log", RichLog)
        log.clear()
        log.write(f"[b]Scanning {len(chosen)} website(s) for contact info…[/b]")
        self._run_scan(chosen)

    def _log(self, msg: str) -> None:
        self.query_one("#results-log", RichLog).write(msg)

    @work(thread=True, exclusive=True)
    def _run_scan(self, chosen: List[Business]) -> None:
        pipeline: Pipeline = self.app.pipeline  # type: ignore[attr-defined]
        progress = lambda m: self.app.call_from_thread(self._log, m)
        try:
            pipeline.scrape_contacts(chosen, progress=progress)
        except Exception as exc:  # pragma: no cover - runtime/browser dependent
            self.app.call_from_thread(self._log, f"[red]Error: {exc}[/red]")
            self.app.call_from_thread(self._reenable)
            return
        self.app.call_from_thread(self._done, chosen)

    def _reenable(self) -> None:
        self.query_one("#scan", Button).disabled = False
        self.query_one("#back", Button).disabled = False

    def _done(self, chosen: List[Business]) -> None:
        self._reenable()
        self.app.contacts = chosen  # type: ignore[attr-defined]
        self.app.push_screen(ContactsScreen())


# --------------------------------------------------------------------------- #
#  Contacts screen – choose which scraped contacts to email
# --------------------------------------------------------------------------- #
class ContactsScreen(Screen):
    """Show scraped contact info; pick who to build emails for."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("a", "select_all", "Select all"),
        Binding("n", "select_none", "Clear"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="contacts-body"):
            yield Static("📇  [b]Contacts found[/b]", classes="title")
            yield Static(
                "Businesses with an email are pre-selected. Space toggles a row. "
                "Advance to compose personalized emails.",
                classes="hint",
            )
            yield SelectionList(id="contacts-list")
            with Horizontal(id="contacts-actions"):
                yield Button("← Back", id="back")
                yield Button("Compose emails →", variant="primary", id="compose")
            yield Static("", id="contacts-summary", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        contacts: List[Business] = self.app.contacts  # type: ignore[attr-defined]
        sel = self.query_one("#contacts-list", SelectionList)
        sel.clear_options()
        with_email = 0
        for idx, b in enumerate(contacts):
            has = b.has_email
            with_email += 1 if has else 0
            prompt = f"{b.name or '(unnamed)'} — {b.contact_line}"
            sel.add_option(Selection(prompt, idx, has))
        sel.focus()
        self.query_one("#contacts-summary", Static).update(
            f"{with_email} of {len(contacts)} businesses have a usable email address."
        )

    def action_select_all(self) -> None:
        self.query_one("#contacts-list", SelectionList).select_all()

    def action_select_none(self) -> None:
        self.query_one("#contacts-list", SelectionList).deselect_all()

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
        pipeline: Pipeline = self.app.pipeline  # type: ignore[attr-defined]
        messages: List[EmailMessage] = []
        for b in recipients:
            try:
                messages.append(pipeline.build_message(b))
            except Exception as exc:
                summary.update(f"[red]Failed to build email for {b.name}: {exc}[/red]")
                return
        self.app.messages = messages  # type: ignore[attr-defined]
        self.app.push_screen(ComposeScreen())


# --------------------------------------------------------------------------- #
#  Compose screen – edit each email before sending
# --------------------------------------------------------------------------- #
class ComposeScreen(Screen):
    """Per-recipient editable subject + HTML body."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

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
            with Horizontal(id="compose-actions"):
                yield Button("← Back", id="back")
                yield Button("Send emails →", variant="primary", id="send")
        yield Footer()

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

    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

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
            yield Rule()
            yield RichLog(id="send-log", highlight=False, markup=True, wrap=True)
        yield Footer()

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

    @on(Button.Pressed, "#restart")
    def _restart(self) -> None:
        self.app.reset_pipeline_state()  # type: ignore[attr-defined]
        self.app.push_screen(SearchScreen())

    @on(Button.Pressed, "#home")
    def _home(self) -> None:
        from .home import HomeScreen
        self.app.push_screen(HomeScreen())
