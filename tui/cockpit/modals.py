"""Modal dialogs for the live call screen: objections, disposition, callback."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from salescall.callflow import DISPOSITIONS, objection_detail_panel
from salescall.objections import ObjectionHandler


class DispositionModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="disp-body"):
            yield Label("Outcome")
            yield OptionList(*[Option(d, id=d) for d in DISPOSITIONS], id="disp-list")
            yield Label("Notes")
            yield Input(id="disp-notes", placeholder="what happened, next steps")
            with Horizontal():
                yield Button("Cancel", id="disp-cancel")
                yield Button("Log", variant="success", id="disp-ok")

    def on_mount(self) -> None:
        ol = self.query_one("#disp-list", OptionList)
        ol.highlighted = 0
        ol.focus()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#disp-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#disp-ok")
    def _ok(self) -> None:
        ol = self.query_one("#disp-list", OptionList)
        idx = ol.highlighted if ol.highlighted is not None else 0
        disposition = DISPOSITIONS[idx]
        notes = self.query_one("#disp-notes", Input).value
        self.dismiss((disposition, notes))


class CallbackModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="cb-body"):
            yield Label("Callback when?")
            yield Input(id="cb-when", placeholder="e.g. tomorrow 2pm")
            yield Label("Notes")
            yield Input(id="cb-notes", placeholder="context")
            with Horizontal():
                yield Button("Cancel", id="cb-cancel")
                yield Button("Log callback", variant="success", id="cb-ok")

    def on_mount(self) -> None:
        self.query_one("#cb-when", Input).focus()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cb-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cb-ok")
    def _ok(self) -> None:
        self.dismiss((
            self.query_one("#cb-when", Input).value,
            self.query_one("#cb-notes", Input).value,
        ))


class ObjectionModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss_none", "Close")]

    def __init__(self, objections: tuple[ObjectionHandler, ...]) -> None:
        super().__init__()
        self._objections = objections

    def compose(self) -> ComposeResult:
        with Vertical(id="obj-body"):
            yield Label("Objection handlers — Enter to view, Esc to close")
            yield OptionList(
                *[Option(o.label, id=str(i)) for i, o in enumerate(self._objections)],
                id="obj-list",
            )
            yield Static("", id="obj-detail")

    def on_mount(self) -> None:
        self.query_one("#obj-list", OptionList).focus()

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    @on(OptionList.OptionSelected, "#obj-list")
    def _show(self, event: OptionList.OptionSelected) -> None:
        o = self._objections[int(event.option.id)]
        self.query_one("#obj-detail", Static).update(objection_detail_panel(o))
