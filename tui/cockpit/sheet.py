"""The prioritized call sheet, rendered as a Textual DataTable."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from salescall import cache
from salescall.models import QueueEntry, Tier
from salescall.prioritize import session_estimate, tier_breakdown

from .data import load_queue

_TIER_LABEL = {
    Tier.NO_SITE_NO_EMAIL: "T1 no-site/email",
    Tier.NO_SITE: "T2 no-site",
    Tier.WEAK_SITE: "T3 weak-site",
    Tier.HAS_SITE: "T4 has-site",
}


class SheetScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="sheet-body"):
            yield Static("📞  [b]Call sheet[/b] — priority order", classes="title")
            yield Static("Loading queue…", id="sheet-empty", classes="hint")
            table = DataTable(id="sheet-table", zebra_stripes=True)
            table.display = False
            yield table
            yield Static("", id="sheet-summary", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._load()

    @work(thread=True, exclusive=True)
    def _load(self) -> None:
        queue = load_queue(".")
        self.app.call_from_thread(self._render_queue, queue)

    def _render_queue(self, queue: list[QueueEntry]) -> None:
        empty = self.query_one("#sheet-empty", Static)
        table = self.query_one("#sheet-table", DataTable)
        callable_q = [e for e in queue if e.tier != Tier.UNCALLABLE]
        if not callable_q:
            empty.update("No scraped data yet — run the pipeline (scrape → contacts) first.")
            return
        empty.display = False
        table.display = True
        table.add_columns("#", "Tier", "Business", "Phone", "Rating", "Local", "Site", "Intel", "Min")
        for pos, e in enumerate(callable_q, 1):
            b = e.business
            if e.local and e.local.display_size > 1:
                dr, ds = e.local.display_rank, e.local.display_size
                marker = "" if e.local.is_real else "~"
                rank_cell = f"{marker}#{dr}/{ds}"
            else:
                rank_cell = "—"
            table.add_row(
                str(pos), _TIER_LABEL.get(e.tier, "?"), b.name[:30],
                b.phone or "—",
                f"{b.rating}★" if b.rating else "—",
                rank_cell,
                "yes" if b.has_website else "NO",
                "✓" if cache.has_intel(b) else "—",
                str(e.suggested_minutes),
            )
        counts = tier_breakdown(queue)
        est = session_estimate(queue)
        self.query_one("#sheet-summary", Static).update(
            f"{counts[Tier.NO_SITE_NO_EMAIL]} hottest · {counts[Tier.NO_SITE]} no-site · "
            f"{counts[Tier.WEAK_SITE]} weak · {counts[Tier.HAS_SITE]} established · "
            f"est. {est} min (~{est/60:.1f} hrs)"
        )
