"""Framework-agnostic call-flow helpers shared by the Rich cockpit
(``salescall.console``) and the Textual cockpit (``tui.cockpit``).

These build the exact Rich renderables the teleprompter shows and enumerate
the playbook's steps. Rendering-only: no input, no side effects.
"""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import QueueEntry, Tier
from .objections import ObjectionHandler
from .playbook import Playbook, Step

_SEV = {"critical": "bold red", "warning": "yellow", "good": "green", "info": "dim"}
_SEV_ICON = {"critical": "🔴", "warning": "🟡", "good": "🟢", "info": "ℹ️ "}

DISPOSITIONS: list[str] = [
    "booked", "callback", "not_interested", "no_answer",
    "voicemail", "wrong_number", "do_not_call", "gatekeeper",
]


def flat_steps(pb: Playbook) -> list[tuple[str, Step]]:
    out: list[tuple[str, Step]] = []
    for stage in pb.stages:
        for step in stage.steps:
            out.append((stage.name, step))
    return out


def brief_panel(entry: QueueEntry, pb: Playbook) -> Panel:
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


def step_panel(stage_name: str, idx: int, total: int, step: Step,
               elapsed: int, budget: int) -> Panel:
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


def objection_detail_panel(o: ObjectionHandler) -> Panel:
    return Panel(
        Group(
            Panel(Text(o.response, style="bold white"), title="🎙  SAY THIS", border_style="green"),
            Text(f"▶ THEN: {o.next_action}", style="cyan"),
            Text(f"↩ IF STILL NO: {o.fallback}", style="yellow") if o.fallback else Text(""),
        ),
        title=f"[bold red]{o.label}[/]", border_style="red",
    )
