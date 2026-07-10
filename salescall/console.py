"""The live call cockpit: a rich-terminal teleprompter the caller drives.

Per call it shows a pre-call brief, then walks the playbook stage-by-stage —
each step displaying SAY / DO / CUE / ANTICIPATE / OPTIONS. The caller advances
with the keyboard, jumps to objection handlers on the fly, and logs the outcome.
"""

from __future__ import annotations

import time

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table

from .callflow import (
    DISPOSITIONS,
    brief_panel,
    flat_steps,
    objection_detail_panel,
    step_panel,
)
from .models import QueueEntry
from .playbook import Playbook, build_playbook
from .scheduler import Session, make_outcome

console = Console()


def _objection_menu(pb: Playbook) -> None:
    table = Table(title="OBJECTION HANDLERS — pick a number", show_lines=False)
    table.add_column("#", style="bold cyan")
    table.add_column("Situation")
    for i, o in enumerate(pb.objections, 1):
        table.add_row(str(i), o.label)
    console.print(table)
    choice = Prompt.ask("Objection # (Enter to go back)", default="").strip()
    if not choice.isdigit():
        return
    idx = int(choice) - 1
    if not 0 <= idx < len(pb.objections):
        return
    o = pb.objections[idx]
    console.print(objection_detail_panel(o))
    Prompt.ask("[dim]Enter to return to the script[/]", default="")


def _help() -> None:
    console.print(Panel(
        "n / Enter → next step    p → previous step\n"
        "o → objection handlers   m → mark outcome & finish call\n"
        "c → log a callback time  b → back to brief\n"
        "s → skip this business   q → quit session    ? → this help",
        title="Cockpit controls", border_style="blue",
    ))


def _run_call(entry: QueueEntry, pb: Playbook, session: Session) -> str:
    """Drive one call. Returns 'quit' to end the whole session, else ''."""
    steps = flat_steps(pb)
    total = len(steps)
    start = time.monotonic()
    i = 0
    console.clear()
    console.print(brief_panel(entry, pb))
    Prompt.ask("[bold green]Dial the number, then press Enter to start the script[/]", default="")

    while True:
        elapsed = int(time.monotonic() - start)
        stage_name, step = steps[i]
        console.clear()
        console.print(step_panel(stage_name, i + 1, total, step, elapsed, entry.suggested_minutes))
        cmd = Prompt.ask("", default="n").strip().lower()

        if cmd in ("n", ""):
            i = min(i + 1, total - 1)
        elif cmd == "p":
            i = max(i - 1, 0)
        elif cmd == "o":
            _objection_menu(pb)
        elif cmd == "b":
            console.clear()
            console.print(brief_panel(entry, pb))
            Prompt.ask("[dim]Enter to return[/]", default="")
        elif cmd == "?":
            _help()
            Prompt.ask("[dim]Enter to return[/]", default="")
        elif cmd == "c":
            when = Prompt.ask("Callback when? (free text, e.g. 'tomorrow 2pm')")
            notes = Prompt.ask("Notes", default="")
            session.record(make_outcome(entry, "callback", notes, elapsed, when))
            console.print("[yellow]Callback logged.[/]")
            return ""
        elif cmd == "s":
            session.record(make_outcome(entry, "no_answer", "skipped", elapsed))
            return ""
        elif cmd == "q":
            return "quit"
        elif cmd == "m":
            disp = _ask_disposition()
            notes = Prompt.ask("Notes (what happened, next steps)", default="")
            session.record(make_outcome(entry, disp, notes, elapsed))
            console.print(f"[bold green]Logged: {disp}[/]")
            return ""


def _ask_disposition() -> str:
    table = Table.grid(padding=(0, 3))
    for i in range(0, len(DISPOSITIONS), 2):
        left = f"[cyan]{i+1}[/] {DISPOSITIONS[i]}"
        right = f"[cyan]{i+2}[/] {DISPOSITIONS[i+1]}" if i + 1 < len(DISPOSITIONS) else ""
        table.add_row(left, right)
    console.print(Panel(table, title="Outcome", border_style="green"))
    choice = Prompt.ask("Disposition #", default="1").strip()
    idx = int(choice) - 1 if choice.isdigit() and 0 <= int(choice) - 1 < len(DISPOSITIONS) else 0
    return DISPOSITIONS[idx]


def run_session(entries: list[QueueEntry], session: Session, intel_for) -> None:
    """Run the cockpit across a list of pending entries.

    intel_for(business) -> WebsiteIntel | None  (cache lookup)
    """
    total = len(entries)
    for n, entry in enumerate(entries, 1):
        entry = entry.with_intel(intel_for(entry.business))
        pb = build_playbook(entry)
        console.print(Rule(f"[bold]Call {n}/{total}[/]"))
        result = _run_call(entry, pb, session)
        if result == "quit":
            console.print("[bold]Session paused. Progress saved — resume anytime.[/]")
            return
        stats = session.stats()
        console.print(Panel(
            "  ".join(f"[cyan]{k}[/]:{v}" for k, v in stats.items()) or "no calls logged yet",
            title=f"Progress  ({n}/{total} this run)", border_style="dim",
        ))
        if n < total:
            go = Prompt.ask("[green]Enter for next call · q to stop[/]", default="").strip().lower()
            if go == "q":
                return
    console.print(Panel("[bold green]Queue complete! 🎉[/]", border_style="green"))
