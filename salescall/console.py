"""The live call cockpit: a rich-terminal teleprompter the caller drives.

Per call it shows a pre-call brief, then walks the playbook stage-by-stage —
each step displaying SAY / DO / CUE / ANTICIPATE / OPTIONS. The caller advances
with the keyboard, jumps to objection handlers on the fly, and logs the outcome.
"""

from __future__ import annotations

import time

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .models import QueueEntry, Tier
from .playbook import Playbook, build_playbook
from .scheduler import Session, make_outcome

console = Console()

_SEV = {"critical": "bold red", "warning": "yellow", "good": "green", "info": "dim"}
_SEV_ICON = {"critical": "🔴", "warning": "🟡", "good": "🟢", "info": "ℹ️ "}

DISPOSITIONS = [
    "booked", "callback", "not_interested", "no_answer",
    "voicemail", "wrong_number", "do_not_call", "gatekeeper",
]


def _brief_panel(entry: QueueEntry, pb: Playbook) -> Panel:
    b = entry.business
    brief = pb.brief
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()
    grid.add_row("Phone", f"[bold green]{brief['phone']}[/]")
    if brief["extra_phones"]:
        grid.add_row("Also", ", ".join(brief["extra_phones"]))
    grid.add_row("Category", f"{brief['category']}  ·  {brief['rating']}  ·  {brief['reviews']} reviews")
    grid.add_row("Location", b.city)
    grid.add_row("Website", brief["website"])
    if brief["stack"] != "—":
        grid.add_row("Built on", brief["stack"])
    if brief["hosting"] != "—":
        grid.add_row("Hosting", brief["hosting"])
    if brief["pagespeed_mobile"] is not None:
        grid.add_row("Mobile speed", f"{brief['pagespeed_mobile']}/100")
    if brief["seo_score"] is not None:
        grid.add_row("Google SEO", f"{brief['seo_score']}/100")
    if brief.get("local_summary"):
        rank_txt = brief["local_summary"]
        if brief.get("local_percentile") is not None:
            rank_txt += f"  (top {100 - int(brief['local_percentile'])}%)" \
                if brief["local_percentile"] < 50 else f"  (beats {int(brief['local_percentile'])}%)"
        grid.add_row("Local rank", f"[bold]{rank_txt}[/]")
    if brief.get("local_distance") is not None:
        grid.add_row("From origin", f"{brief['local_distance']} mi")

    blocks = [grid]
    if brief.get("local_competitors_above"):
        lc = Text("\n⚔ RANKED ABOVE THEM (your pitch target):\n", style="bold red")
        for c in brief["local_competitors_above"]:
            lc.append(f"   {c}\n", style="red")
        if brief.get("local_nearest"):
            lc.append(f"   closest rival: {brief['local_nearest']}\n", style="dim")
        blocks.append(lc)
    if brief["top_points"]:
        tp = Text("\n★ TOP TALKING POINTS\n", style="bold magenta")
        for i, p in enumerate(brief["top_points"][:4], 1):
            tp.append(f"  {i}. {p}\n", style="white")
        blocks.append(tp)
    if brief["strengths"]:
        st = Text("\n✓ Their strengths (acknowledge these): ", style="bold green")
        st.append(", ".join(brief["strengths"]), style="green")
        blocks.append(st)

    tier_label = {
        Tier.NO_SITE_NO_EMAIL: "TIER 1 · HOTTEST — no site, no email",
        Tier.NO_SITE: "TIER 2 — no website",
        Tier.WEAK_SITE: "TIER 3 — weak site",
        Tier.HAS_SITE: "TIER 4 — established site",
    }.get(entry.tier, "")
    return Panel(
        Group(*blocks),
        title=f"[bold white]{b.name}[/]   [dim]({tier_label} · ~{entry.suggested_minutes} min)[/]",
        border_style="cyan",
    )


def _step_panel(stage_name: str, idx: int, total: int, step, elapsed: int, budget: int) -> Panel:
    body = []
    if step.say:
        body.append(Panel(Text(step.say, style="bold white"), title="🎙  SAY", border_style="green"))
    if step.do:
        body.append(Text(f"▶ DO: {step.do}", style="cyan"))
    if step.cue:
        body.append(Text(f"⏸  {step.cue}", style="bold yellow"))
    if step.anticipate:
        t = Text("👂 ANTICIPATE:\n", style="dim")
        for a in step.anticipate:
            t.append(f"     • {a}\n", style="italic dim")
        body.append(t)
    if step.options:
        t = Text("🔀 OPTIONS:\n", style="magenta")
        for o in step.options:
            t.append(f"     → {o}\n", style="magenta")
        body.append(t)

    over = elapsed > budget * 60
    timer = f"[{'red' if over else 'green'}]{elapsed // 60}:{elapsed % 60:02d}[/] / {budget}:00"
    return Panel(
        Group(*body),
        title=f"[bold]{stage_name}[/]  step {idx}/{total}",
        subtitle=f"⏱ {timer}   [dim]n=next p=prev o=objections m=outcome c=callback ?=help[/]",
        border_style="white",
    )


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
    console.print(Panel(
        Group(
            Panel(Text(o.response, style="bold white"), title="🎙  SAY THIS", border_style="green"),
            Text(f"▶ THEN: {o.next_action}", style="cyan"),
            Text(f"↩ IF STILL NO: {o.fallback}", style="yellow") if o.fallback else Text(""),
        ),
        title=f"[bold red]{o.label}[/]", border_style="red",
    ))
    Prompt.ask("[dim]Enter to return to the script[/]", default="")


def _help() -> None:
    console.print(Panel(
        "n / Enter → next step    p → previous step\n"
        "o → objection handlers   m → mark outcome & finish call\n"
        "c → log a callback time  b → back to brief\n"
        "s → skip this business   q → quit session    ? → this help",
        title="Cockpit controls", border_style="blue",
    ))


def _flat_steps(pb: Playbook):
    out = []
    for stage in pb.stages:
        for step in stage.steps:
            out.append((stage.name, step))
    return out


def _run_call(entry: QueueEntry, pb: Playbook, session: Session) -> str:
    """Drive one call. Returns 'quit' to end the whole session, else ''."""
    steps = _flat_steps(pb)
    total = len(steps)
    start = time.monotonic()
    i = 0
    console.clear()
    console.print(_brief_panel(entry, pb))
    Prompt.ask("[bold green]Dial the number, then press Enter to start the script[/]", default="")

    while True:
        elapsed = int(time.monotonic() - start)
        stage_name, step = steps[i]
        console.clear()
        console.print(_step_panel(stage_name, i + 1, total, step, elapsed, entry.suggested_minutes))
        cmd = Prompt.ask("", default="n").strip().lower()

        if cmd in ("n", ""):
            i = min(i + 1, total - 1)
        elif cmd == "p":
            i = max(i - 1, 0)
        elif cmd == "o":
            _objection_menu(pb)
        elif cmd == "b":
            console.clear()
            console.print(_brief_panel(entry, pb))
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
