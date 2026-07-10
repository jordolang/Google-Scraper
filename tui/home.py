"""The landing screen: pick which tool to open."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option


class HomeScreen(Screen):
    """Two entries: the email pipeline and the sales-call cockpit."""

    BINDINGS = [Binding("escape", "app.quit", "Quit"), Binding("q", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="home-body"):
            yield Static("📇  [b]Jlang.dev Outreach Suite[/b]", classes="title")
            yield Static("Choose a tool. Esc/q quits.", classes="hint")
            menu = OptionList(
                Option("🔍  Scrape → Contact → Email", id="pipeline"),
                Option("📞  Sales Call Cockpit", id="cockpit"),
                id="home-menu",
            )
            yield menu
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#home-menu", OptionList).focus()

    @on(OptionList.OptionSelected, "#home-menu")
    def _choose(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "pipeline":
            from .pipeline_screens import SearchScreen
            self.app.push_screen(SearchScreen())
        elif event.option.id == "cockpit":
            from .cockpit.menu import CockpitMenuScreen
            self.app.push_screen(CockpitMenuScreen())
