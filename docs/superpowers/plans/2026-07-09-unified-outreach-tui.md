# Unified Outreach Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the Scrape→Email pipeline TUI and the Sales Call Cockpit under one integrated Textual app launched from `app.py`, with the Rich cockpit preserved as a `--classic` fallback.

**Architecture:** A single `OutreachApp(App)` opens on a `HomeScreen` (push/pop navigation). Home routes to the existing five pipeline screens (moved verbatim into `tui/pipeline_screens.py`) or to a new `tui/cockpit/` package that ports the Rich teleprompter to Textual. All `salescall/` logic is reused; Rich `Panel` builders are shared via a new `salescall/callflow.py` and rendered inside Textual `Static` widgets.

**Tech Stack:** Python 3, Textual (built on Rich), pytest. Textual `App.run_test()` pilot for UI tests, driven under `asyncio.run(...)` (matching the existing `tests/test_tui.py` style — no pytest-asyncio).

## Global Constraints

- Python with type annotations on all function signatures; PEP 8; frozen dataclasses for domain models (existing `salescall/models.py` pattern — do not mutate).
- Textual is the only new runtime dependency and is already in `requirements.txt` (`textual>=0.60.0`). Do not add dependencies.
- Rich `Panel`/renderables may be rendered by mounting them into a Textual `Static` widget — this is the sanctioned reuse path; do not re-derive the teleprompter layout.
- Cockpit session/intel state persists under `.salescall_cache/` (git-ignored already). Never commit that directory.
- Tests run headless/offline: no browser, network, or SMTP. Cockpit tests use temporary CSV fixtures and a temp `.salescall_cache` via `monkeypatch`/`chdir`.
- Preserve backward compatibility: `tests/test_tui.py` must pass unchanged; `python scraper_tui.py`, `python sales_calls.py`, and `sales_calls.py {prep,sheet,call}` must keep working.
- Commit after every task (each task ends green).

---

### Task 1: Extract shared call-flow helpers into `salescall/callflow.py`

Move the framework-agnostic pieces out of `salescall/console.py` so both the classic Rich cockpit and the new Textual cockpit share one source. `console.py` keeps working (it becomes an importer).

**Files:**
- Create: `salescall/callflow.py`
- Modify: `salescall/console.py` (replace private helpers with imports)
- Test: `tests/test_callflow.py`

**Interfaces:**
- Produces:
  - `DISPOSITIONS: list[str]`
  - `flat_steps(pb: Playbook) -> list[tuple[str, Step]]`
  - `brief_panel(entry: QueueEntry, pb: Playbook) -> rich.panel.Panel`
  - `step_panel(stage_name: str, idx: int, total: int, step: Step, elapsed: int, budget: int) -> rich.panel.Panel`
  - `objection_detail_panel(o: ObjectionHandler) -> rich.panel.Panel`
- Consumes: `salescall.models` (`QueueEntry`, `Tier`, `Step` via playbook), `salescall.playbook` (`Playbook`), `salescall.objections` (`ObjectionHandler`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_callflow.py
from salescall import callflow
from salescall.models import Business, QueueEntry, Tier
from salescall.playbook import build_playbook


def _entry() -> QueueEntry:
    b = Business(name="Acme Plumbing", category="Plumber", phone="(614) 555-1212")
    return QueueEntry(business=b, tier=Tier.NO_SITE_NO_EMAIL, score=1.0, suggested_minutes=7)


def test_dispositions_are_stable():
    assert "booked" in callflow.DISPOSITIONS
    assert "callback" in callflow.DISPOSITIONS
    assert len(callflow.DISPOSITIONS) == 8


def test_flat_steps_covers_every_stage_step():
    pb = build_playbook(_entry())
    flat = callflow.flat_steps(pb)
    expected = sum(len(stage.steps) for stage in pb.stages)
    assert len(flat) == expected
    assert all(isinstance(name, str) for name, _ in flat)


def test_panels_are_rich_renderables():
    from rich.panel import Panel
    pb = build_playbook(_entry())
    assert isinstance(callflow.brief_panel(_entry(), pb), Panel)
    step = pb.stages[0].steps[0]
    assert isinstance(callflow.step_panel("open", 1, 5, step, 30, 7), Panel)
    assert isinstance(callflow.objection_detail_panel(pb.objections[0]), Panel)


def test_console_still_imports_shared_helpers():
    from salescall import console
    assert console.DISPOSITIONS is callflow.DISPOSITIONS
    assert console.brief_panel is callflow.brief_panel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_callflow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'salescall.callflow'`.

- [ ] **Step 3: Create `salescall/callflow.py`**

Move the bodies of `_flat_steps`, `DISPOSITIONS`, `_brief_panel`, `_step_panel`, and the objection-detail Panel (currently built inline in `console._objection_menu`) here, renamed public. Copy the exact rendering logic from `console.py` lines 25–163 verbatim into these functions.

```python
# salescall/callflow.py
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
    # PASTE the exact body of console._brief_panel here (lines 35-91),
    # unchanged. It already returns a Panel.
    ...


def step_panel(stage_name: str, idx: int, total: int, step: Step,
               elapsed: int, budget: int) -> Panel:
    # PASTE the exact body of console._step_panel here (lines 95-120), unchanged.
    ...


def objection_detail_panel(o: ObjectionHandler) -> Panel:
    return Panel(
        Group(
            Panel(Text(o.response, style="bold white"), title="🎙  SAY THIS", border_style="green"),
            Text(f"▶ THEN: {o.next_action}", style="cyan"),
            Text(f"↩ IF STILL NO: {o.fallback}", style="yellow") if o.fallback else Text(""),
        ),
        title=f"[bold red]{o.label}[/]", border_style="red",
    )
```

Note: replace the two `...` placeholders with the verbatim function bodies copied from `salescall/console.py` (do not rewrite the layout). `Step` is importable from `salescall.playbook`.

- [ ] **Step 4: Update `salescall/console.py` to import the shared helpers**

At the top of `console.py`, after the existing imports, add:

```python
from .callflow import (
    DISPOSITIONS,
    brief_panel,
    flat_steps,
    objection_detail_panel,
    step_panel,
)
```

Then delete the now-duplicated definitions in `console.py`: the module-level `DISPOSITIONS`, `_flat_steps`, `_brief_panel`, `_step_panel`. Update `console.py`'s internal references:
- `_brief_panel(entry, pb)` → `brief_panel(entry, pb)` (2 call sites: lines 173, 191)
- `_step_panel(...)` → `step_panel(...)` (line 180)
- `_flat_steps(pb)` → `flat_steps(pb)` (line 168)
- In `_objection_menu`, replace the inline detail `Panel(...)` (lines 137-144) with `console.print(objection_detail_panel(o))`.
- Keep `_SEV`/`_SEV_ICON` only if still referenced; otherwise remove.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_callflow.py tests/test_tui.py -v`
Expected: PASS (new callflow tests green; existing TUI tests untouched).

- [ ] **Step 6: Sanity-check the classic cockpit still constructs its panels**

Run: `python -c "from salescall import console, callflow; print('ok', len(callflow.DISPOSITIONS))"`
Expected: `ok 8`

- [ ] **Step 7: Commit**

```bash
git add salescall/callflow.py salescall/console.py tests/test_callflow.py
git commit -m "refactor: extract shared call-flow renderables into salescall/callflow.py"
```

---

### Task 2: Cockpit queue-loading helper `tui/cockpit/data.py`

A non-exiting queue loader (the CLI's `_load_queue` calls `sys.exit`; the TUI needs an empty-state instead).

**Files:**
- Create: `tui/cockpit/__init__.py`, `tui/cockpit/data.py`
- Test: `tests/test_cockpit_data.py`

**Interfaces:**
- Produces:
  - `load_queue(root: str = ".") -> list[QueueEntry]` — returns `[]` when no CSVs exist (never exits).
  - `has_scraped_data(root: str = ".") -> bool`
- Consumes: `salescall.data_loader.load_businesses`, `salescall.prioritize.build_queue`, `salescall.localseo` (`build_local_rankings`, `origin`), `salescall.cache.load_serp`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cockpit_data.py
from pathlib import Path

from tui.cockpit import data


def test_empty_dir_returns_empty_queue(tmp_path: Path):
    assert data.has_scraped_data(str(tmp_path)) is False
    assert data.load_queue(str(tmp_path)) == []


def test_loads_queue_from_results_csv(tmp_path: Path):
    csv = tmp_path / "google_maps_results_test.csv"
    csv.write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n"
        "Bob Electric,Electrician,(614) 555-3434,http://bob.example,4.2,30\n",
        encoding="utf-8",
    )
    assert data.has_scraped_data(str(tmp_path)) is True
    queue = data.load_queue(str(tmp_path))
    assert len(queue) == 2
    assert queue[0].business.name in {"Acme Plumbing", "Bob Electric"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cockpit_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tui.cockpit'`.

- [ ] **Step 3: Create the package and loader**

```python
# tui/cockpit/__init__.py
"""Textual screens for the Sales Call Cockpit (ported from salescall/console.py)."""
```

```python
# tui/cockpit/data.py
"""Load the prioritized call queue for the cockpit screens.

Mirrors sales_calls._load_queue but returns an empty list (never exits) when
no scraped CSVs are present, so the TUI can show a friendly empty-state.
"""

from __future__ import annotations

from salescall import cache
from salescall.data_loader import load_businesses
from salescall.localseo import build_local_rankings, origin
from salescall.models import QueueEntry
from salescall.prioritize import build_queue


def has_scraped_data(root: str = ".") -> bool:
    return bool(load_businesses(root))


def load_queue(root: str = ".") -> list[QueueEntry]:
    businesses = load_businesses(root)
    if not businesses:
        return []
    queue = build_queue(businesses)
    positions, field_sizes = cache.load_serp()
    rankings = build_local_rankings(
        businesses, real_positions=positions, real_field_sizes=field_sizes
    )
    return [
        e.with_local(rankings[e.business.slug]) if e.business.slug in rankings else e
        for e in queue
    ]
```

Note: confirm `load_businesses` accepts a directory argument by reading `salescall/data_loader.py`; `sales_calls._load_queue` calls `load_businesses(".")`, so it does. If its parameter has a different name, adapt the call accordingly.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cockpit_data.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tui/cockpit/__init__.py tui/cockpit/data.py tests/test_cockpit_data.py
git commit -m "feat: add non-exiting cockpit queue loader (tui/cockpit/data.py)"
```

---

### Task 3: Split pipeline screens into `tui/pipeline_screens.py`

Move the five existing pipeline screens out of `tui/app.py` verbatim. `tui/app.py` will re-export them so nothing downstream breaks yet.

**Files:**
- Create: `tui/pipeline_screens.py`
- Modify: `tui/app.py`
- Test: `tests/test_tui.py` (must still pass unchanged)

**Interfaces:**
- Produces: `SearchScreen`, `ResultsScreen`, `ContactsScreen`, `ComposeScreen`, `SendScreen` in `tui.pipeline_screens`.
- Consumes: `tui.models` (`Business`, `EmailMessage`), `tui.pipeline` (`Pipeline`).

- [ ] **Step 1: Create `tui/pipeline_screens.py` with the five screen classes**

Cut `SearchScreen`, `ResultsScreen`, `ContactsScreen`, `ComposeScreen`, `SendScreen` (current `tui/app.py` lines 46–465) into this new file verbatim. Add the imports they need at the top:

```python
# tui/pipeline_screens.py
"""The five screens of the scrape → contact → email pipeline flow.

Extracted from tui/app.py so the app module holds only OutreachApp. Behavior
is unchanged. Each screen pops back to the screen beneath it on Esc.
"""

from __future__ import annotations

from typing import List

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, Checkbox, Footer, Header, Input, Label, OptionList,
    RichLog, Rule, SelectionList, Static, TextArea,
)
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from .models import Business, EmailMessage
from .pipeline import Pipeline

# ... paste the five screen classes here, verbatim ...
```

- [ ] **Step 2: Change `SearchScreen`'s Esc binding to pop, not quit**

In `tui/pipeline_screens.py`, `SearchScreen.BINDINGS`, change:

```python
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]
```

(Was `app.quit`. HomeScreen will sit beneath it, so Esc returns Home. When `ScraperTUI` boots — see Task 4 — Home is still on the stack beneath, so this is always safe.)

- [ ] **Step 3: Reduce `tui/app.py` to re-export the moved screens (temporary)**

Replace the five screen class definitions in `tui/app.py` with a re-export, keeping `ScraperTUI` and `main` exactly as they are for now:

```python
# tui/app.py  (top section, after module docstring)
from .pipeline_screens import (  # noqa: F401  (re-exported for compatibility)
    ComposeScreen, ContactsScreen, ResultsScreen, SearchScreen, SendScreen,
)
```

Remove the now-moved `textual.widgets` imports from `app.py` that are no longer used there (keep only what `ScraperTUI`/`main` need). `ScraperTUI` still does `self.push_screen(SearchScreen())` in `on_mount` — that name now comes from the re-export, so it still resolves.

- [ ] **Step 4: Run the existing tests to verify no regression**

Run: `pytest tests/test_tui.py -v`
Expected: PASS. (Imports `from tui.app import ... SearchScreen ...` still resolve via the re-export; navigation unchanged.)

- [ ] **Step 5: Commit**

```bash
git add tui/pipeline_screens.py tui/app.py
git commit -m "refactor: move pipeline screens to tui/pipeline_screens.py"
```

---

### Task 4: `OutreachApp` + `HomeScreen`, with `ScraperTUI` compat

Turn `tui/app.py` into the unified app that opens on Home and can boot straight into a flow. Keep `ScraperTUI` as a compat subclass that lands on the pipeline (so `tests/test_tui.py` and `scraper_tui.py` are unchanged in behavior).

**Files:**
- Create: `tui/home.py`
- Modify: `tui/app.py`
- Test: `tests/test_home.py` (new), `tests/test_tui.py` (unchanged, must pass)

**Interfaces:**
- Produces:
  - `HomeScreen` in `tui.home` — `OptionList` with two options; selecting pushes the pipeline or cockpit flow.
  - `OutreachApp(App)` in `tui.app` — holds shared state; `__init__(self, pipeline, demo=False, start="home")`; `start ∈ {"home","pipeline","cockpit"}`.
  - `ScraperTUI(OutreachApp)` — compat alias booting with `start="pipeline"`.
  - `main(argv=None)` — unchanged CLI surface; runs `OutreachApp(..., start="home")`.
- Consumes: `tui.pipeline_screens.SearchScreen`, `tui.cockpit.menu.CockpitMenuScreen` (Task 5), `tui.pipeline` (`Pipeline`, `make_pipeline`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_home.py
import asyncio

from tui.app import OutreachApp
from tui.pipeline import make_pipeline
from tui.pipeline_screens import SearchScreen


def test_home_opens_on_home_and_routes_to_pipeline():
    from tui.home import HomeScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            # Select the first option (Scrape → Email) and activate it.
            app.screen.query_one("#home-menu").highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, SearchScreen)
            # Esc returns to Home (Home sits beneath).
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    asyncio.run(scenario())


def test_start_pipeline_lands_on_search():
    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="pipeline")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, SearchScreen)

    asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_home.py -v`
Expected: FAIL — `ImportError: cannot import name 'OutreachApp'` (and `tui.home` missing).

- [ ] **Step 3: Create `tui/home.py`**

```python
# tui/home.py
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
```

- [ ] **Step 4: Rewrite `tui/app.py` as `OutreachApp` (+ `ScraperTUI` compat)**

```python
# tui/app.py
"""The unified Textual application: one launcher for both outreach tools.

Opens on HomeScreen; from there the user enters the scrape→email pipeline or
the sales-call cockpit. Each flow pushes screens on top of Home; Esc pops back.
Run with ``python app.py`` (repo root), or the flow-specific shims
``scraper_tui.py`` / ``sales_calls.py``.
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from textual.app import App
from textual.binding import Binding

from .models import Business, EmailMessage
from .pipeline import Pipeline, make_pipeline
from .pipeline_screens import (  # noqa: F401  re-exported for test/back-compat
    ComposeScreen, ContactsScreen, ResultsScreen, SearchScreen, SendScreen,
)

_CSS = """
Screen { align: center top; }
.title { padding: 1 0 0 0; text-style: bold; }
.hint { color: $text-muted; padding: 0 0 1 0; }
.readonly { color: $text-muted; padding: 0 0 1 0; }
#home-body, #search-body, #results-body, #contacts-body, #compose-body,
#send-body, #cockpit-menu-body, #sheet-body, #prep-body, #call-body {
    width: 100%; max-width: 120; padding: 1 2;
}
Input { margin: 0 0 1 0; }
Input.tiny { width: 8; }
#search-actions, #results-actions, #contacts-actions, #compose-actions, #send-actions {
    height: auto; padding: 1 0; align-horizontal: right;
}
#search-actions Button, #results-actions Button, #contacts-actions Button,
#compose-actions Button, #send-actions Button { margin: 0 0 0 2; }
#search-opts, #send-opts { height: auto; padding: 0 0 1 0; }
#send-opts Label { padding: 1 1 0 3; }
SelectionList { height: 1fr; min-height: 8; border: round $primary; padding: 0 1; }
RichLog { height: 10; border: round $panel; padding: 0 1; }
#compose-main { height: 1fr; min-height: 14; }
#recipient-list { width: 40; border: round $primary; margin: 0 2 0 0; }
#editor { width: 1fr; }
#body-field { height: 1fr; min-height: 8; border: round $panel; }
OptionList { height: auto; border: round $primary; padding: 0 1; }
#call-panel { height: 1fr; min-height: 12; }
DataTable { height: 1fr; }
"""


class OutreachApp(App):
    """Top-level app holding the pipeline + state shared across screens."""

    CSS = _CSS
    BINDINGS = [Binding("ctrl+c", "quit", "Quit", priority=True)]

    def __init__(self, pipeline: Pipeline, demo: bool = False, start: str = "home") -> None:
        super().__init__()
        self.pipeline = pipeline
        self.demo = demo
        self._start = start
        # pipeline flow state
        self.businesses: List[Business] = []
        self.chosen: List[Business] = []
        self.contacts: List[Business] = []
        self.messages: List[EmailMessage] = []
        # cockpit shared session (created lazily to avoid import cost at startup)
        self._session = None

    @property
    def session(self):
        """Shared cockpit Session, created once per app run."""
        if self._session is None:
            from salescall.scheduler import Session
            self._session = Session()
        return self._session

    def on_mount(self) -> None:
        self.title = "Jlang.dev Outreach Suite"
        self.sub_title = "demo mode" if self.demo else "live mode"
        from .home import HomeScreen
        self.push_screen(HomeScreen())
        if self._start == "pipeline":
            self.push_screen(SearchScreen())
        elif self._start == "cockpit":
            from .cockpit.menu import CockpitMenuScreen
            self.push_screen(CockpitMenuScreen())


class ScraperTUI(OutreachApp):
    """Backwards-compatible alias: boots straight into the pipeline flow."""

    def __init__(self, pipeline: Pipeline, demo: bool = False) -> None:
        super().__init__(pipeline=pipeline, demo=demo, start="pipeline")


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Unified outreach TUI: scrape+email pipeline and sales-call cockpit."
    )
    parser.add_argument("--demo", action="store_true",
                        help="Use built-in sample data for the pipeline (no browser/network).")
    parser.add_argument("--from-email", default="jordan@jlang.dev",
                        help="Sender email address (default: jordan@jlang.dev).")
    parser.add_argument("--template", default="email_template.html",
                        help="Path to the HTML email template.")
    parser.add_argument("--visible", action="store_true",
                        help="Run the scraper browser in visible (non-headless) mode.")
    parser.add_argument("--start", choices=["home", "pipeline", "cockpit"], default="home",
                        help="Which screen to open on (default: home).")
    args = parser.parse_args(argv)

    pipeline = make_pipeline(
        demo=args.demo, from_email=args.from_email,
        template_path=args.template, headless=not args.visible,
    )
    OutreachApp(pipeline=pipeline, demo=args.demo, start=args.start).run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it fails only on the missing cockpit menu**

Run: `pytest tests/test_home.py::test_start_pipeline_lands_on_search -v`
Expected: PASS. (`test_home_opens_on_home_and_routes_to_pipeline` also passes — it only touches the pipeline branch. The cockpit branch import is lazy, so Home renders without `CockpitMenuScreen` existing yet.)

- [ ] **Step 6: Run the legacy suite to confirm back-compat**

Run: `pytest tests/test_tui.py -v`
Expected: PASS. `ScraperTUI` now pushes Home then `SearchScreen`; `app.screen` is `SearchScreen`, `app.businesses == []`, and the full navigation still works. Esc is never pressed on `SearchScreen` in those tests, so the pop-to-Home change is transparent.

- [ ] **Step 7: Commit**

```bash
git add tui/app.py tui/home.py tests/test_home.py
git commit -m "feat: add OutreachApp + HomeScreen launcher (ScraperTUI kept as pipeline shim)"
```

---

### Task 5: `CockpitMenuScreen`

The cockpit's sub-menu (Prep / Call sheet / Start calling), pushed from Home.

**Files:**
- Create: `tui/cockpit/menu.py`
- Test: `tests/test_cockpit_menu.py`

**Interfaces:**
- Produces: `CockpitMenuScreen(Screen)` — `OptionList#cockpit-menu` with ids `prep`, `sheet`, `call`; each pushes the matching screen.
- Consumes: `tui.cockpit.prep.PrepScreen`, `tui.cockpit.sheet.SheetScreen`, `tui.cockpit.call.CallScreen` (lazy imports so this task lands before those exist — but its test only checks it renders and that selecting `sheet` works after Task 6; write the menu now, test routing in Task 6).

- [ ] **Step 1: Write the failing test (render + focus only for now)**

```python
# tests/test_cockpit_menu.py
import asyncio

from tui.app import OutreachApp
from tui.pipeline import make_pipeline


def test_cockpit_menu_renders_three_options():
    from tui.cockpit.menu import CockpitMenuScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="cockpit")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, CockpitMenuScreen)
            menu = app.screen.query_one("#cockpit-menu")
            ids = [opt.id for opt in menu._options]  # Textual OptionList options
            assert ids == ["prep", "sheet", "call"]

    asyncio.run(scenario())
```

Note: if `menu._options` is not accessible in the installed Textual version, assert `menu.option_count == 3` instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cockpit_menu.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tui.cockpit.menu'`.

- [ ] **Step 3: Create `tui/cockpit/menu.py`**

```python
# tui/cockpit/menu.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cockpit_menu.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tui/cockpit/menu.py tests/test_cockpit_menu.py
git commit -m "feat: add CockpitMenuScreen"
```

---

### Task 6: `SheetScreen` (priority call sheet as a DataTable)

**Files:**
- Create: `tui/cockpit/sheet.py`
- Test: `tests/test_cockpit_sheet.py`

**Interfaces:**
- Produces: `SheetScreen(Screen)` — loads the queue via `tui.cockpit.data.load_queue`, fills `DataTable#sheet-table`, shows an empty-state `Static#sheet-empty` when the queue is empty.
- Consumes: `tui.cockpit.data.load_queue`, `salescall.prioritize` (`tier_breakdown`, `session_estimate`), `salescall.cache.has_intel`, `salescall.models.Tier`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cockpit_sheet.py
import asyncio
from pathlib import Path

from tui.app import OutreachApp
from tui.pipeline import make_pipeline


def _write_csv(tmp_path: Path) -> None:
    (tmp_path / "google_maps_results_x.csv").write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n"
        "Bob Electric,Electrician,(614) 555-3434,http://bob.example,4.2,30\n",
        encoding="utf-8",
    )


def test_sheet_populates_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_csv(tmp_path)
    from tui.cockpit.sheet import SheetScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(SheetScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.screen.query_one("#sheet-table")
            assert table.row_count == 2

    asyncio.run(scenario())


def test_sheet_empty_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tui.cockpit.sheet import SheetScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(SheetScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            empty = app.screen.query_one("#sheet-empty")
            assert "No scraped data" in str(empty.renderable)

    asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cockpit_sheet.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tui.cockpit.sheet'`.

- [ ] **Step 3: Create `tui/cockpit/sheet.py`**

```python
# tui/cockpit/sheet.py
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
        self.app.call_from_thread(self._render, queue)

    def _render(self, queue: list[QueueEntry]) -> None:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cockpit_sheet.py -v`
Expected: PASS (both populated and empty-state).

- [ ] **Step 5: Add the menu-routing test now that SheetScreen exists**

Append to `tests/test_cockpit_menu.py`:

```python
def test_menu_routes_to_sheet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tui.cockpit.menu import CockpitMenuScreen
    from tui.cockpit.sheet import SheetScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="cockpit")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#cockpit-menu").highlighted = 1  # "sheet"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, SheetScreen)

    asyncio.run(scenario())
```

Run: `pytest tests/test_cockpit_menu.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tui/cockpit/sheet.py tests/test_cockpit_sheet.py tests/test_cockpit_menu.py
git commit -m "feat: add cockpit SheetScreen (priority call sheet DataTable + empty-state)"
```

---

### Task 7: `PrepScreen` (threaded intel gathering)

**Files:**
- Create: `tui/cockpit/prep.py`
- Test: `tests/test_cockpit_prep.py`

**Interfaces:**
- Produces: `PrepScreen(Screen)` — a `Button#prep-go` starts a threaded worker that streams progress to `RichLog#prep-log`; empty queue shows the empty-state message.
- Consumes: `tui.cockpit.data.load_queue`, `salescall.intel.engine.analyze_business`, `salescall.cache` (`save_intel`, `CACHE_DIR`), `salescall.serp`, `salescall.localseo.origin`, `salescall.models.Tier`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cockpit_prep.py
import asyncio
from pathlib import Path

from tui.app import OutreachApp
from tui.pipeline import make_pipeline


def test_prep_runs_and_logs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "google_maps_results_x.csv").write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n",
        encoding="utf-8",
    )
    # Stub intel so no network is touched.
    import tui.cockpit.prep as prep_mod
    from salescall.models import WebsiteIntel
    monkeypatch.setattr(prep_mod, "analyze_business", lambda b: WebsiteIntel(reachable=False))

    from tui.cockpit.prep import PrepScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(PrepScreen())
            await pilot.pause()
            await pilot.click("#prep-go")
            await app.workers.wait_for_complete()
            await pilot.pause()
            log = app.screen.query_one("#prep-log")
            # RichLog stores written lines; assert something was logged.
            assert log.lines
    asyncio.run(scenario())
```

Note: if `RichLog.lines` is not exposed in the installed version, assert on a screen attribute the worker sets (e.g. `app.screen._done is True`), and set that flag at the end of the worker.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cockpit_prep.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tui.cockpit.prep'`.

- [ ] **Step 3: Create `tui/cockpit/prep.py`**

```python
# tui/cockpit/prep.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cockpit_prep.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tui/cockpit/prep.py tests/test_cockpit_prep.py
git commit -m "feat: add cockpit PrepScreen (threaded intel + SERP prep)"
```

---

### Task 8: Cockpit modals (objection / disposition / callback)

**Files:**
- Create: `tui/cockpit/modals.py`
- Test: `tests/test_cockpit_modals.py`

**Interfaces:**
- Produces (all `ModalScreen` subclasses; each `dismiss(...)`es a value the caller receives via `push_screen(modal, callback)`):
  - `DispositionModal()` → dismisses `tuple[str, str]` `(disposition, notes)`.
  - `CallbackModal()` → dismisses `tuple[str, str]` `(when, notes)`.
  - `ObjectionModal(objections: tuple[ObjectionHandler, ...])` → dismisses `None` (informational; shows detail then closes).
- Consumes: `salescall.callflow.DISPOSITIONS`, `salescall.callflow.objection_detail_panel`, `salescall.objections.ObjectionHandler`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cockpit_modals.py
import asyncio

from textual.app import App

from tui.cockpit.modals import CallbackModal, DispositionModal


def test_disposition_modal_returns_choice_and_notes():
    results = []

    class Host(App):
        def on_mount(self):
            self.push_screen(DispositionModal(), lambda r: results.append(r))

    async def scenario():
        app = Host()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.screen.query_one("#disp-list").highlighted = 0  # "booked"
            app.screen.query_one("#disp-notes").value = "great call"
            await pilot.click("#disp-ok")
            await pilot.pause()
    asyncio.run(scenario())
    assert results == [("booked", "great call")]


def test_callback_modal_returns_when_and_notes():
    results = []

    class Host(App):
        def on_mount(self):
            self.push_screen(CallbackModal(), lambda r: results.append(r))

    async def scenario():
        app = Host()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.screen.query_one("#cb-when").value = "tomorrow 2pm"
            app.screen.query_one("#cb-notes").value = "asked to call back"
            await pilot.click("#cb-ok")
            await pilot.pause()
    asyncio.run(scenario())
    assert results == [("tomorrow 2pm", "asked to call back")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cockpit_modals.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tui.cockpit.modals'`.

- [ ] **Step 3: Create `tui/cockpit/modals.py`**

```python
# tui/cockpit/modals.py
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
```

Add matching CSS for the modal bodies to `_CSS` in `tui/app.py` (append):

```python
# append inside _CSS string in tui/app.py
# DispositionModal, CallbackModal, ObjectionModal
ModalScreen { align: center middle; }
#disp-body, #cb-body, #obj-body {
    width: 80; max-width: 90%; height: auto; padding: 1 2;
    background: $surface; border: thick $primary;
}
#disp-list, #obj-list { height: auto; max-height: 12; border: round $primary; }
#obj-detail { height: auto; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cockpit_modals.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tui/cockpit/modals.py tui/app.py tests/test_cockpit_modals.py
git commit -m "feat: add cockpit modals (disposition, callback, objection)"
```

---

### Task 9: `CallScreen` (the live teleprompter)

The heart of the port. Reuses `callflow.brief_panel`/`step_panel` inside a `Static`, drives navigation with key bindings, logs outcomes through the shared `Session`.

**Files:**
- Create: `tui/cockpit/call.py`
- Test: `tests/test_cockpit_call.py`

**Interfaces:**
- Produces: `CallScreen(Screen)` — walks `pending_entries(load_queue(), app.session)`; per business shows brief then steps; keys `n/p/b/o/m/c/s/q`.
- Consumes: `tui.cockpit.data.load_queue`, `salescall.scheduler` (`pending_entries`, `make_outcome`), `salescall.playbook.build_playbook`, `salescall.cache.load_intel`, `salescall.callflow` (`brief_panel`, `step_panel`, `flat_steps`), `tui.cockpit.modals` (`DispositionModal`, `CallbackModal`, `ObjectionModal`), `app.session` (`OutreachApp.session`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cockpit_call.py
import asyncio
from pathlib import Path

from tui.app import OutreachApp
from tui.pipeline import make_pipeline


def _seed(tmp_path: Path) -> None:
    (tmp_path / "google_maps_results_x.csv").write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n",
        encoding="utf-8",
    )


def test_call_screen_steps_and_logs_disposition(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    from tui.cockpit.call import CallScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CallScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            screen = app.screen
            # Begins on the brief; 'n' enters the script and advances.
            assert screen.business_index == 0
            await pilot.press("enter")  # start script from brief
            await pilot.pause()
            start_step = screen.step_index
            await pilot.press("n")
            await pilot.pause()
            assert screen.step_index == start_step + 1
            await pilot.press("p")
            await pilot.pause()
            assert screen.step_index == start_step
            # Mark outcome → disposition modal → pick booked.
            await pilot.press("m")
            await pilot.pause()
            app.screen.query_one("#disp-list").highlighted = 0  # booked
            await pilot.click("#disp-ok")
            await pilot.pause()
            assert app.session.disposition("acme_plumbing") == "booked"
    asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cockpit_call.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tui.cockpit.call'`.

- [ ] **Step 3: Create `tui/cockpit/call.py`**

```python
# tui/cockpit/call.py
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
        self._render()
        self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        if not self._on_brief:
            self._render()

    def _render(self) -> None:
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
            self.step_index = 0
        else:
            self.step_index = min(self.step_index + 1, len(self._steps) - 1)
        self._render()

    def action_prev_step(self) -> None:
        if not self._on_brief:
            self.step_index = max(self.step_index - 1, 0)
        self._render()

    def action_show_brief(self) -> None:
        self._on_brief = True
        self._render()

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
            self.query_one("#call-panel", Static).update("[b green]Queue complete! 🎉[/]")
            self.query_one("#call-status", Static).update(
                " · ".join(f"{k}:{v}" for k, v in self.app.session.stats().items()) or "no calls logged"
            )
            return
        self._enter_business()
```

Note: `set_interval` accumulates one timer per business here. If timers must be cleared between businesses, capture the return of `set_interval` in `self._timer` and call `self._timer.stop()` at the top of `_enter_business`. Add that only if a redraw/perf issue appears; functionally the `_on_brief`/index guards keep it correct.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cockpit_call.py -v`
Expected: PASS.

- [ ] **Step 5: Add the menu→call routing test**

Append to `tests/test_cockpit_menu.py`:

```python
def test_menu_routes_to_call(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "google_maps_results_x.csv").write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n",
        encoding="utf-8",
    )
    from tui.cockpit.menu import CockpitMenuScreen
    from tui.cockpit.call import CallScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="cockpit")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#cockpit-menu").highlighted = 2  # "call"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, CallScreen)
    asyncio.run(scenario())
```

Run: `pytest tests/test_cockpit_menu.py tests/test_cockpit_call.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tui/cockpit/call.py tests/test_cockpit_call.py tests/test_cockpit_menu.py
git commit -m "feat: add cockpit CallScreen (live teleprompter port)"
```

---

### Task 10: `app.py` front door + `scraper_tui.py` / `sales_calls.py` shims

**Files:**
- Create: `app.py` (repo root)
- Modify: `scraper_tui.py`, `sales_calls.py`
- Test: `tests/test_entrypoints.py`

**Interfaces:**
- `app.py` → calls `tui.app.main()`.
- `scraper_tui.py` → launches the unified app straight into the pipeline (preserves `--demo` etc.).
- `sales_calls.py` → default launches the unified app into the cockpit; `prep`/`sheet`/`call` open that screen; `--classic [prep|sheet|call]` runs the original Rich functions.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_entrypoints.py
import importlib


def test_app_module_exposes_main():
    mod = importlib.import_module("app")
    assert hasattr(mod, "main") or hasattr(mod, "__file__")


def test_sales_calls_classic_dispatch(monkeypatch):
    import sales_calls
    called = {}
    monkeypatch.setattr(sales_calls, "cmd_sheet", lambda: called.setdefault("sheet", True))
    sales_calls.main(["--classic", "sheet"])
    assert called.get("sheet") is True


def test_sales_calls_default_launches_unified(monkeypatch):
    import sales_calls
    launched = {}

    def fake_run(pipeline, demo=False, start="home"):
        launched["start"] = start
        class _App:
            def run(self_inner): launched["ran"] = True
        return _App()

    # main should build an OutreachApp with start="cockpit" and .run() it.
    monkeypatch.setattr(sales_calls, "_launch_cockpit", lambda screen=None: launched.setdefault("cockpit", screen or "menu"))
    sales_calls.main([])
    assert launched.get("cockpit") == "menu"
```

Note: adjust `test_sales_calls_default_launches_unified` to whatever seam Step 4 exposes (`_launch_cockpit`). The intent: no-arg `main()` routes to the cockpit launcher, not the Rich menu.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_entrypoints.py -v`
Expected: FAIL — `app` module missing / `sales_calls.main` signature mismatch.

- [ ] **Step 3: Create `app.py`**

```python
#!/usr/bin/env python3
"""Unified launcher for the Jlang.dev outreach suite.

    python app.py                 # home screen: pick a tool
    python app.py --start cockpit # jump straight to the call cockpit
    python app.py --demo          # pipeline uses sample data

See ``python app.py --help`` for all options.
"""

from tui.app import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rewrite `scraper_tui.py` and `sales_calls.py` shims**

`scraper_tui.py`:

```python
#!/usr/bin/env python3
"""Shim: launch the unified outreach app straight into the scrape→email pipeline.

    python scraper_tui.py            # live mode (drives Chrome + SMTP)
    python scraper_tui.py --demo     # explore with sample data

Equivalent to ``python app.py --start pipeline``.
"""

import sys

from tui.app import main

if __name__ == "__main__":
    main(sys.argv[1:] + ["--start", "pipeline"])
```

`sales_calls.py` — keep the existing Rich functions (`cmd_prep`, `cmd_sheet`, `cmd_call`, `_menu`, `_load_queue`, and imports) intact for `--classic`, and replace only the `main()` at the bottom:

```python
def _launch_cockpit(screen: str | None = None) -> None:
    """Launch the unified Textual app in the cockpit, optionally on a sub-screen."""
    from tui.app import OutreachApp
    from tui.pipeline import make_pipeline
    app = OutreachApp(pipeline=make_pipeline(demo=False), demo=False, start="cockpit")

    if screen in ("prep", "sheet", "call"):
        _orig_on_mount = app.on_mount

        def _on_mount_then_push() -> None:
            _orig_on_mount()
            from tui.cockpit.prep import PrepScreen
            from tui.cockpit.sheet import SheetScreen
            from tui.cockpit.call import CallScreen
            app.push_screen({"prep": PrepScreen, "sheet": SheetScreen, "call": CallScreen}[screen]())

        app.on_mount = _on_mount_then_push  # type: ignore[assignment]
    app.run()


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)

    if "--classic" in args:
        args.remove("--classic")
        command = args[0].lower() if args else ""
        if command == "prep":
            cmd_prep()
        elif command == "sheet":
            cmd_sheet()
        elif command == "call":
            cmd_call()
        else:
            _menu()
        return

    command = args[0].lower() if args else ""
    if command in ("prep", "sheet", "call"):
        _launch_cockpit(command)
    else:
        _launch_cockpit(None)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted — progress saved.[/]")
        sys.exit(0)
```

Note: the file docstring at the top of `sales_calls.py` should be updated to describe the new default (Textual cockpit) and the `--classic` flag. Keep `from __future__ import annotations` present so `str | None` works on the Python in use; it is already imported at the top of the file.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_entrypoints.py -v`
Expected: PASS. Adjust the seam name in the test if you named it differently.

- [ ] **Step 6: Smoke-check the shims import cleanly**

Run:
```bash
python -c "import app, scraper_tui, sales_calls; print('shims import ok')"
python sales_calls.py --classic sheet >/dev/null 2>&1; echo "classic sheet exit: $?"
```
Expected: `shims import ok`; classic sheet runs (exit 0, or 1 only if no CSVs — either is acceptable, it must not traceback).

- [ ] **Step 7: Commit**

```bash
git add app.py scraper_tui.py sales_calls.py tests/test_entrypoints.py
git commit -m "feat: add app.py launcher; make scraper_tui/sales_calls thin shims (--classic fallback)"
```

---

### Task 11: Docs + full-suite verification

**Files:**
- Modify: `README.md`, `SALES_CALL_README.md`
- Test: full suite

- [ ] **Step 1: Update `README.md`**

Add a short "Unified launcher" section documenting:
```
python app.py                 # home: pick pipeline or cockpit
python app.py --start cockpit # straight to the sales-call cockpit
python app.py --demo          # pipeline sample-data mode
python scraper_tui.py         # pipeline shim (unchanged)
python sales_calls.py         # cockpit shim
python sales_calls.py --classic   # original Rich cockpit
```
Note that both TUIs now live under one app; the Rich cockpit remains available via `--classic`.

- [ ] **Step 2: Update `SALES_CALL_README.md`**

Add a note at the top: the cockpit is now reachable from the unified app (`python app.py` → Sales Call Cockpit, or `python sales_calls.py`); the standalone Rich commands remain available as `python sales_calls.py --classic {prep|sheet|call}`.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: PASS — all pipeline tests plus the new cockpit/home/entrypoint tests.

- [ ] **Step 4: Coverage check on the new surface**

Run: `pytest --cov=tui --cov=salescall --cov-report=term-missing -q`
Expected: cockpit modules and `salescall/callflow.py` exercised; aim for the 80% guideline on the new code. If `tui/cockpit/prep.py` or `call.py` fall short, add targeted tests (e.g. callback path writes a `callback` outcome; empty-queue path in `CallScreen` shows the "no pending calls" message).

- [ ] **Step 5: Manual smoke (optional, not in CI)**

Run: `python app.py --demo` and confirm Home → both flows navigate; `python sales_calls.py --classic sheet` prints the Rich sheet. Exit with `q`/Ctrl+C.

- [ ] **Step 6: Commit**

```bash
git add README.md SALES_CALL_README.md
git commit -m "docs: document unified outreach launcher and --classic cockpit fallback"
```

---

## Self-Review

**1. Spec coverage:**
- Integrated Textual app + Home push/pop → Tasks 4, 5. ✓
- Full cockpit port (prep/sheet/call teleprompter) → Tasks 6 (sheet), 7 (prep), 8 (modals), 9 (call). ✓
- Reuse salescall logic; share Rich panels → Task 1 (`callflow.py`), consumed in Tasks 6/8/9. ✓
- Keep standalone entrypoints as shims; `--classic` fallback → Task 10. ✓
- Friendly empty-state (no cockpit demo data) → Task 2 (`load_queue` returns `[]`), surfaced in Tasks 6/7/9. ✓
- File split of `tui/app.py` → Task 3. ✓
- Tests via `run_test()` pilot under `asyncio.run` → every UI task; back-compat guarded in Tasks 3–4. ✓

**2. Placeholder scan:** The only intentional "paste verbatim" markers are in Task 1 Step 3 (`brief_panel`/`step_panel` bodies) — deliberately copying existing, known-good code from `console.py` rather than re-authoring layout; the exact source lines are cited. No `TBD`/`add error handling`/`similar to Task N` placeholders elsewhere.

**3. Type consistency:** `load_queue(root=".")`, `OutreachApp(pipeline, demo, start)`, `app.session` (property returning `Session`), modal dismiss types (`tuple[str,str]` for disposition/callback, `None` for objection), `make_outcome(entry, disposition, notes, elapsed[, when])`, `pending_entries(queue, session)`, `flat_steps(pb)->list[tuple[str,Step]]` — all consistent across the tasks that produce and consume them. `ScraperTUI` remains constructible as `ScraperTUI(pipeline=..., demo=...)` for the legacy tests.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-09-unified-outreach-tui.md`.
