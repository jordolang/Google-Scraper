"""Sales Call Cockpit sub-menu: prep intel, view the sheet, or start calling."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option


class CockpitMenuScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="cockpit-menu-body"):
            yield Static("📞  [b]Sales Call Cockpit[/b]", classes="title")
            yield Static("Prep intel, review the call sheet, or start calling.", classes="hint")
            yield OptionList(
                Option("1  Prep intel (analyze + cache every website)", id="prep"),
                Option("2  Call sheet (priority schedule)", id="sheet"),
                Option("3  Start calling (live cockpit)", id="call"),
                id="cockpit-menu",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#cockpit-menu", OptionList).focus()

    @on(OptionList.OptionSelected, "#cockpit-menu")
    def _choose(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "prep":
            from .prep import PrepScreen
            self.app.push_screen(PrepScreen())
        elif event.option.id == "sheet":
            from .sheet import SheetScreen
            self.app.push_screen(SheetScreen())
        elif event.option.id == "call":
            from .call import CallScreen
            self.app.push_screen(CallScreen())
