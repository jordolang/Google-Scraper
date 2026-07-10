"""The live call cockpit as a Textual screen — the teleprompter the caller drives.

Per business: shows a pre-call brief, then walks the playbook step-by-step with
a live timer. Keys advance/retreat, open objection handlers, and log outcomes to
the shared Session (persisted under .salescall_cache/).
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from salescall import cache
from salescall.callflow import brief_panel, flat_steps, step_panel
from salescall.models import QueueEntry
from salescall.playbook import Playbook, Step, build_playbook
from salescall.scheduler import make_outcome, pending_entries

from .data import load_queue
from .modals import CallbackModal, DispositionModal, ObjectionModal


class CallScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q", "app.pop_screen", "Quit cockpit"),
        Binding("n,right,enter", "next_step", "Next"),
        Binding("p,left", "prev_step", "Prev"),
        Binding("b", "show_brief", "Brief"),
        Binding("o", "objections", "Objections"),
        Binding("m", "mark_outcome", "Outcome"),
        Binding("c", "callback", "Callback"),
        Binding("s", "skip", "Skip"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.pending: List[QueueEntry] = []
        self.business_index: int = 0
        self.step_index: int = 0
        self._steps: List[Tuple[str, Step]] = []
        self._pb: Optional[Playbook] = None
        self._on_brief: bool = True
        self._start_monotonic: float = 0.0
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="call-body"):
            yield Static("Loading queue…", id="call-panel")
            yield Static("", id="call-status", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._load()

    def _elapsed(self) -> int:
        return int(time.monotonic() - self._start_monotonic) if self._start_monotonic else 0

    # ---- loading & per-business setup ------------------------------------ #
    def _load(self) -> None:
        queue = load_queue(".")
        self.pending = pending_entries(queue, self.app.session)
        if not self.pending:
            self.query_one("#call-panel", Static).update(
                "No pending calls — run prep/scrape first, or the queue is complete."
            )
            return
        self.business_index = 0
        self._enter_business()

    def _enter_business(self) -> None:
        entry = self.pending[self.business_index]
        entry = entry.with_intel(cache.load_intel(entry.business))
        self._pb = build_playbook(entry)
        self._steps = flat_steps(self._pb)
        self.step_index = 0
        self._on_brief = True
        self._start_monotonic = time.monotonic()
        self._entry = entry
        self._render_view()
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        if not self._on_brief:
            self._render_view()

    def _render_view(self) -> None:
        panel = self.query_one("#call-panel", Static)
        if self._on_brief:
            panel.update(brief_panel(self._entry, self._pb))
            self.query_one("#call-status", Static).update(
                "Dial the number, then press Enter to start the script."
            )
            return
        stage_name, step = self._steps[self.step_index]
        panel.update(step_panel(
            stage_name, self.step_index + 1, len(self._steps), step,
            self._elapsed(), self._entry.suggested_minutes,
        ))
        n = self.business_index + 1
        self.query_one("#call-status", Static).update(
            f"Call {n}/{len(self.pending)} · n/p step · o objections · m outcome · c callback · s skip · q quit"
        )

    # ---- step navigation -------------------------------------------------- #
    def action_next_step(self) -> None:
        if self._on_brief:
            self._on_brief = False
        else:
            self.step_index = min(self.step_index + 1, len(self._steps) - 1)
        self._render_view()

    def action_prev_step(self) -> None:
        if not self._on_brief:
            self.step_index = max(self.step_index - 1, 0)
        self._render_view()

    def action_show_brief(self) -> None:
        self._on_brief = True
        self._render_view()

    # ---- objections / outcomes ------------------------------------------- #
    def action_objections(self) -> None:
        if self._pb:
            self.app.push_screen(ObjectionModal(self._pb.objections))

    def action_mark_outcome(self) -> None:
        def _done(result: Optional[Tuple[str, str]]) -> None:
            if result is None:
                return
            disposition, notes = result
            self.app.session.record(
                make_outcome(self._entry, disposition, notes, self._elapsed())
            )
            self._advance()
        self.app.push_screen(DispositionModal(), _done)

    def action_callback(self) -> None:
        def _done(result: Optional[Tuple[str, str]]) -> None:
            if result is None:
                return
            when, notes = result
            self.app.session.record(
                make_outcome(self._entry, "callback", notes, self._elapsed(), when)
            )
            self._advance()
        self.app.push_screen(CallbackModal(), _done)

    def action_skip(self) -> None:
        self.app.session.record(
            make_outcome(self._entry, "no_answer", "skipped", self._elapsed())
        )
        self._advance()

    # ---- advance to next business ---------------------------------------- #
    def _advance(self) -> None:
        self.business_index += 1
        if self.business_index >= len(self.pending):
            if self._timer is not None:
                self._timer.stop()
            self.query_one("#call-panel", Static).update("[b green]Queue complete! 🎉[/]")
            self.query_one("#call-status", Static).update(
                " · ".join(f"{k}:{v}" for k, v in self.app.session.stats().items()) or "no calls logged"
            )
            return
        self._enter_business()
