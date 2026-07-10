"""Gather + cache website intel (and optional real SERP rankings) for the queue."""

from __future__ import annotations

import os
import time

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from salescall import cache, serp
from salescall.intel.engine import analyze_business
from salescall.localseo import origin
from salescall.models import Tier

from .data import load_queue


class PrepScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._done = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="prep-body"):
            yield Static("🛠  [b]Prep intel[/b]", classes="title")
            yield Static(
                "Analyzes and caches each website's SEO/hosting/speed so calls "
                "load instant briefs. Runs in the background; safe to re-run.",
                classes="hint",
            )
            with Horizontal(id="prep-actions"):
                yield Button("Start prep", variant="primary", id="prep-go")
            yield RichLog(id="prep-log", highlight=False, markup=True, wrap=True)
        yield Footer()

    def _log(self, msg: str) -> None:
        self.query_one("#prep-log", RichLog).write(msg)

    @on(Button.Pressed, "#prep-go")
    def _start(self) -> None:
        self.query_one("#prep-go", Button).disabled = True
        self.query_one("#prep-log", RichLog).clear()
        self._run()

    @work(thread=True, exclusive=True)
    def _run(self, throttle: float = 2.0) -> None:
        log = lambda m: self.app.call_from_thread(self._log, m)
        queue = load_queue(".")
        callable_entries = [e for e in queue if e.tier != Tier.UNCALLABLE]
        if not callable_entries:
            log("[yellow]No scraped data yet — run the pipeline first.[/]")
            self.app.call_from_thread(self._finish)
            return

        if serp.available():
            log(f"[b]Fetching real SERP rankings via {serp.provider_name()}…[/]")
            businesses = [e.business for e in queue]
            positions, field_sizes = serp.gather_real_positions(businesses, origin())
            if positions:
                cache.save_serp(positions, field_sizes)
                log(f"[green]✓ matched {len(positions)} real Google positions[/]")
            else:
                log("[yellow]No SERP matches (check key/quota); using proxy ranking.[/]")
        else:
            log("[dim]No SERPAPI_KEY — using prominence proxy for local ranking.[/]")

        if not os.environ.get("PAGESPEED_API_KEY"):
            log("[yellow]Tip: set PAGESPEED_API_KEY for reliable speed scores.[/]")
        log(f"[b]Prepping intel for {len(callable_entries)} businesses…[/]")

        for n, entry in enumerate(callable_entries, 1):
            b = entry.business
            try:
                intel = analyze_business(b)
                cache.save_intel(b, intel)
                tag = "no-site" if not b.has_website else (
                    f"speed={intel.pagespeed_mobile} {len(intel.selling_points)} levers"
                )
                log(f"  [{n}/{len(callable_entries)}] {b.name[:40]} [green]✓[/] {tag}")
            except Exception as exc:  # noqa: BLE001 — one bad site must not kill the batch
                log(f"  [{n}/{len(callable_entries)}] {b.name[:40]} [red]✗ {type(exc).__name__}[/]")
            if b.has_website and n < len(callable_entries):
                time.sleep(throttle)

        log(f"[b green]Intel cached to {cache.CACHE_DIR}/[/]")
        self.app.call_from_thread(self._finish)

    def _finish(self) -> None:
        self._done = True
        self.query_one("#prep-go", Button).disabled = False
