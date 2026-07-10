#!/usr/bin/env python3
"""
Sales Call Cockpit — Jlang.dev outreach.

Turns scraped business data into a prioritized phone-call campaign:
  prep   Build the queue + gather/cache website intel for every business
  sheet  Print the prioritized call schedule
  call   Launch the live interactive call cockpit (teleprompter)

Run with no arguments for an interactive menu.

Optional environment:
  PAGESPEED_API_KEY   Free Google key for reliable PageSpeed scores in batch
                      (https://developers.google.com/speed/docs/insights/v5/get-started)
"""

from __future__ import annotations

import sys
import time

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from salescall import cache
from salescall.data_loader import load_businesses
from salescall.intel.engine import analyze_business
from salescall import serp
from salescall.localseo import build_local_rankings, origin
from salescall.models import QueueEntry, Tier
from salescall.prioritize import build_queue, session_estimate, tier_breakdown
from salescall.scheduler import Session, pending_entries

console = Console()

_TIER_LABEL = {
    Tier.NO_SITE_NO_EMAIL: "T1 no-site/no-email",
    Tier.NO_SITE: "T2 no-site",
    Tier.WEAK_SITE: "T3 weak-site",
    Tier.HAS_SITE: "T4 has-site",
    Tier.UNCALLABLE: "—  uncallable",
}


def _load_queue() -> list[QueueEntry]:
    businesses = load_businesses(".")
    if not businesses:
        console.print("[red]No scraped CSVs found (google_maps_results_*.csv / contact_details_*.csv).[/]")
        sys.exit(1)
    queue = build_queue(businesses)
    # Local SEO is relative — compute across the whole set, then attach to each.
    # Use cached real SERP positions when available; otherwise the proxy.
    positions, field_sizes = cache.load_serp()
    rankings = build_local_rankings(businesses, real_positions=positions,
                                    real_field_sizes=field_sizes)
    return [
        e.with_local(rankings[e.business.slug]) if e.business.slug in rankings else e
        for e in queue
    ]


def cmd_prep(throttle: float = 2.0) -> None:
    """Gather and cache website intel + real SERP rankings for every business."""
    queue = _load_queue()
    callable_entries = [e for e in queue if e.tier != Tier.UNCALLABLE]

    # Real local-pack rankings (cached), if a SERP provider key is configured.
    if serp.available():
        console.print(f"[bold]Fetching real SERP rankings via {serp.provider_name()}...[/]")
        businesses = [e.business for e in queue]
        positions, field_sizes = serp.gather_real_positions(businesses, origin())
        if positions:
            cache.save_serp(positions, field_sizes)
            console.print(f"[green]✓ matched real Google positions for {len(positions)} businesses[/]")
        else:
            console.print("[yellow]No SERP matches returned (check key/quota); using proxy ranking.[/]")
    else:
        console.print("[dim]No SERPAPI_KEY set — local ranking uses the prominence proxy. "
                      "Set SERPAPI_KEY in .env for real local-pack positions.[/]")

    console.print(f"[bold]Prepping intel for {len(callable_entries)} businesses...[/]")
    if not __import__("os").environ.get("PAGESPEED_API_KEY"):
        console.print("[yellow]Tip: set PAGESPEED_API_KEY for reliable speed scores "
                      "(keyless is rate-limited).[/]")

    for n, entry in enumerate(callable_entries, 1):
        b = entry.business
        console.print(f"  [{n}/{len(callable_entries)}] {b.name[:40]:40} ", end="")
        try:
            intel = analyze_business(b)
            cache.save_intel(b, intel)
            tag = "no-site" if not b.has_website else (
                f"speed={intel.pagespeed_mobile} {len(intel.selling_points)} levers"
            )
            console.print(f"[green]✓[/] {tag}")
        except Exception as exc:  # noqa: BLE001 - never let one site kill the batch
            console.print(f"[red]✗ {type(exc).__name__}[/]")
        if b.has_website and n < len(callable_entries):
            time.sleep(throttle)
    console.print(f"[bold green]Intel cached to {cache.CACHE_DIR}/[/]")


def cmd_sheet() -> None:
    """Print the prioritized call schedule."""
    queue = _load_queue()
    counts = tier_breakdown(queue)
    est = session_estimate(queue)

    table = Table(title="📞 CALL SHEET (priority order)", show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Tier", style="cyan")
    table.add_column("Business")
    table.add_column("Phone", style="green")
    table.add_column("Rating", justify="center")
    table.add_column("Local rank", justify="center")
    table.add_column("Site", justify="center")
    table.add_column("Intel", justify="center")
    table.add_column("Min", justify="right")

    pos = 0
    for e in queue:
        if e.tier == Tier.UNCALLABLE:
            continue
        pos += 1
        b = e.business
        if e.local and e.local.display_size > 1:
            dr, ds = e.local.display_rank, e.local.display_size
            half = dr > ds // 2
            marker = "" if e.local.is_real else "~"
            rank_cell = (f"[{'red' if half else 'green'}]{marker}#{dr}/{ds}[/] "
                         f"[dim]{e.local.field[:10]}[/]")
        else:
            rank_cell = "[dim]—[/]"
        table.add_row(
            str(pos), _TIER_LABEL[e.tier], b.name[:30],
            b.phone or "—",
            f"{b.rating}★" if b.rating else "—",
            rank_cell,
            "yes" if b.has_website else "[bold red]NO[/]",
            "[green]✓[/]" if cache.has_intel(b) else "[dim]—[/]",
            str(e.suggested_minutes),
        )
    console.print(table)
    console.print(
        f"\n[bold]{counts[Tier.NO_SITE_NO_EMAIL]}[/] hottest (no site+email) · "
        f"[bold]{counts[Tier.NO_SITE]}[/] no-site · [bold]{counts[Tier.WEAK_SITE]}[/] weak · "
        f"[bold]{counts[Tier.HAS_SITE]}[/] established · "
        f"[dim]{counts[Tier.UNCALLABLE]} uncallable[/]"
    )
    console.print(f"Estimated calling time: [bold]{est} min (~{est/60:.1f} hrs)[/]")
    if any(not cache.has_intel(e.business) for e in queue if e.tier != Tier.UNCALLABLE):
        console.print("[yellow]Some businesses have no cached intel — run 'prep' first for full briefs.[/]")


def cmd_call() -> None:
    """Launch the live call cockpit over the pending queue."""
    from salescall.console import run_session

    queue = _load_queue()
    session = Session()
    pending = pending_entries(queue, session)
    if not pending:
        console.print("[bold green]No pending calls — queue complete or all logged![/]")
        return
    console.print(f"[bold]{len(pending)} calls pending.[/] Starting cockpit...\n")
    run_session(pending, session, cache.load_intel)


def _menu() -> None:
    console.print("[bold cyan]\n📞 SALES CALL COCKPIT — Jlang.dev[/]")
    console.print("1. Prep intel (analyze + cache every website)")
    console.print("2. View call sheet (priority schedule)")
    console.print("3. Start calling (live cockpit)")
    console.print("4. Quit")
    choice = Prompt.ask("Choose", choices=["1", "2", "3", "4"], default="2")
    if choice == "1":
        cmd_prep()
    elif choice == "2":
        cmd_sheet()
    elif choice == "3":
        cmd_call()


def main() -> None:
    args = sys.argv[1:]
    if not args:
        _menu()
        return
    command = args[0].lower()
    if command == "prep":
        cmd_prep()
    elif command == "sheet":
        cmd_sheet()
    elif command == "call":
        cmd_call()
    else:
        console.print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted — progress saved.[/]")
        sys.exit(0)
