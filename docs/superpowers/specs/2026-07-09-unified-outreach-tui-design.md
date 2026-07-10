# Unified Outreach Suite — Design Spec

**Date:** 2026-07-09
**Status:** Approved (pending spec review)
**Branch:** `claude/unified-outreach-tui`

## Goal

Unify the two existing terminal UIs — the **Scrape → Contact → Email pipeline** (Textual, `scraper_tui.py` + `tui/`) and the **Sales Call Cockpit** (Rich, `sales_calls.py` + `salescall/`) — under a single integrated Textual application with one front door.

## Decisions (from brainstorming)

| Decision | Choice |
|----------|--------|
| Unification style | One integrated Textual app (port the Rich cockpit to Textual) |
| Navigation | Home screen + push/pop screens; `Esc` = back |
| Cockpit port scope | Full faithful port: Prep, Call sheet, and live teleprompter |
| Standalone entrypoints | Keep `sales_calls.py` + `scraper_tui.py` as thin shims into their flow |
| Old Rich teleprompter | **Keep** as `--classic` fallback (not retired) |
| Cockpit + no CSVs | Friendly empty-state (no cockpit demo data this pass) |

## Architecture

```
app.py  (new front door)  →  OutreachApp(App)
   OutreachApp.on_mount → push HomeScreen
      HomeScreen                         ▸ Scrape → Email      ▸ Call Cockpit
        ├─ pipeline flow (existing, moved verbatim):
        │    SearchScreen → ResultsScreen → ContactsScreen → ComposeScreen → SendScreen
        └─ CockpitMenuScreen             ▸ Prep intel  ▸ Call sheet  ▸ Start calling
             ├─ PrepScreen   — threaded intel/SERP worker + progress RichLog
             ├─ SheetScreen  — DataTable priority schedule
             └─ CallScreen   — live teleprompter (ported from salescall/console.py)
```

- **Navigation:** every screen binds `escape` to `app.pop_screen` (the pipeline already does this); `HomeScreen` binds `escape`/`q` to quit. Selecting **Call Cockpit** pushes `CockpitMenuScreen`, whose three entries push the Prep/Sheet/Call screens. Two-level nesting mirrors today's `sales_calls.py` menu and keeps each flow full-screen.
- **Shared app state:** `OutreachApp` holds the pipeline state that the pipeline screens already read (`pipeline`, `businesses`, `chosen`, `contacts`, `messages`) plus a single cockpit `Session` (created once per run so pause/resume is consistent). The `demo` flag applies to the pipeline only.

## Reuse vs. rebuild

**Reused as-is (no changes):** the whole `salescall/` logic layer — `data_loader`, `prioritize`, `localseo`, `scheduler` (`Session`, `pending_entries`, `make_outcome`), `playbook` (`build_playbook`), `intel.engine.analyze_business`, `cache`, `models`, `serp`, `objections`.

**Rebuilt in Textual (presentation only):**
- `salescall/console.py` Rich teleprompter → `tui/cockpit/call.py`
- `sales_calls.py` Rich menu/tables → `tui/cockpit/menu.py`, `sheet.py`, `prep.py`

**Extracted for sharing:** the two framework-agnostic bits currently inside `salescall/console.py` — the `DISPOSITIONS` list and the `_flat_steps(playbook)` flattener — move to a small shared module `salescall/callflow.py`. Both the retained Rich path (`console.py`) and the new Textual `call.py` import them, so there is exactly one source of truth. `console.py` keeps working (it's the `--classic` fallback).

## The teleprompter port (`tui/cockpit/call.py`)

`CallScreen(Screen)` state:
- `pending: list[QueueEntry]` (from `pending_entries(queue, session)`)
- `business_index: int`, `step_index: int`
- `steps: list[tuple[str, Step]]` for the current business (via shared `flat_steps`)
- `call_started_at` / elapsed seconds (via `set_interval(1, tick)` — no busy polling)
- shared `Session` from `self.app`

Rendering per step reproduces the Rich panels as Textual widgets: a **SAY** panel, and **DO / CUE / ANTICIPATE / OPTIONS** blocks, plus a header (`stage step i/total`) and a live timer that turns red past `suggested_minutes`. A pre-call **brief** view (phone, category, rating, website, tech/hosting/speed/SEO, local rank, competitors-ranked-above, top talking points, strengths, tier) shows before stepping and is reachable again with `b`.

Key bindings (replacing the Rich `Prompt.ask` command loop):

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| `n` / `right` / `enter` | next step | `o` | objection handler (modal) |
| `p` / `left` | previous step | `m` | mark outcome → disposition modal |
| `b` | back to brief | `c` | log callback (modal) |
| `s` | skip business (`no_answer`) | `q` | quit cockpit → back to menu |
| `?` | help overlay | | |

**Modals** (`ModalScreen` subclasses in `tui/cockpit/modals.py`):
- `ObjectionModal` — `OptionList` of `playbook.objections`; picking one shows SAY / THEN / IF-STILL-NO, dismiss returns to the script.
- `DispositionModal` — `OptionList` of `DISPOSITIONS` + a notes `Input`; returns `(disposition, notes)`.
- `CallbackModal` — "when" `Input` + notes `Input`; returns `(when, notes)`.

Outcomes are written via the unchanged `Session.record(make_outcome(...))`, persisting to `.salescall_cache/session.json` (shared with the classic path). After a business is dispositioned/skipped, advance to the next pending entry; when the queue is exhausted, show a "queue complete" state and allow `Esc` back to the menu. Between businesses, a progress line shows `Session.stats()`.

## Prep & Sheet screens

- **`PrepScreen`** — reuses the `@work(thread=True, exclusive=True)` + `call_from_thread` progress pattern from `SearchScreen`. It performs the `cmd_prep` sequence: optional real-SERP fetch (`serp.available()` → `serp.gather_real_positions` → `cache.save_serp`), then `analyze_business` + `cache.save_intel` per callable entry, streaming per-business progress to a `RichLog`. One business failing never kills the batch (existing behavior). Surfaces the same `PAGESPEED_API_KEY` / `SERPAPI_KEY` hints.
- **`SheetScreen`** — a Textual `DataTable` reproducing the `cmd_sheet` columns (#, Tier, Business, Phone, Rating, Local rank, Site, Intel-cached, Min) plus the tier-breakdown + estimated-time summary and the "run prep first" hint when intel is missing.

## Threading, loading & empty-state

- Queue loading (`data_loader.load_businesses` + `build_queue` + `build_local_rankings`) runs in a worker on cockpit entry, with a brief "loading…" state.
- **Empty-state:** if no `google_maps_results_*.csv` / `contact_details_*.csv` exist, cockpit screens render a clear "No scraped data yet — run the pipeline first" message instead of `sys.exit(1)` (the CLI's current behavior). No cockpit demo data.

## File organization (targeted cleanup)

`tui/app.py` is 540 lines mixing five screens + the app class. Split as part of this work:

| File | Contents |
|------|----------|
| `tui/app.py` | `OutreachApp` only — shared state, merged CSS, `on_mount` → HomeScreen |
| `tui/home.py` | `HomeScreen` |
| `tui/pipeline_screens.py` | the five existing pipeline screens (moved verbatim, imports adjusted) |
| `tui/cockpit/__init__.py` | package marker |
| `tui/cockpit/menu.py` | `CockpitMenuScreen` |
| `tui/cockpit/prep.py` | `PrepScreen` |
| `tui/cockpit/sheet.py` | `SheetScreen` |
| `tui/cockpit/call.py` | `CallScreen` |
| `tui/cockpit/modals.py` | `ObjectionModal`, `DispositionModal`, `CallbackModal` |
| `tui/cockpit/data.py` | queue-loading helper shared by prep/sheet/call (wraps `_load_queue` logic) |

CSS currently on `ScraperTUI` moves to `OutreachApp`, extended with cockpit-screen rules.

## Entrypoints (thin shims)

- **`app.py`** (new, root) — parses the same pipeline args (`--demo`, `--from-email`, `--template`, `--visible`), builds the pipeline, runs `OutreachApp`, opens on `HomeScreen`.
- **`scraper_tui.py`** — unchanged CLI surface; launches `OutreachApp` and auto-pushes the pipeline flow (`SearchScreen`) so `python scraper_tui.py [--demo ...]` lands exactly where it does today.
- **`sales_calls.py`** — launches `OutreachApp` and auto-pushes the cockpit:
  - no args → `CockpitMenuScreen`
  - `prep` / `sheet` / `call` → auto-push that cockpit screen (muscle memory preserved)
  - `--classic [prep|sheet|call]` → the original Rich behavior (`cmd_prep`/`cmd_sheet`/`cmd_call` / `_menu`) unchanged

## Error handling

- Worker exceptions surface to the screen's log (pipeline pattern) — never crash the app.
- Per-business intel failures are caught and logged; the batch continues.
- Missing CSVs → empty-state, not exit.
- Missing API keys → informational hints; proxy ranking / keyless PageSpeed still work.
- `Session` save/load already tolerates corrupt/missing JSON (returns gracefully).

## Testing

Extend `tests/test_tui.py` using Textual's `async with app.run_test() as pilot` harness:

1. **Routing** — Home → pipeline flow; Home → cockpit menu; cockpit menu → prep/sheet/call.
2. **Empty-state** — cockpit with no CSVs shows the empty-state message (no exit).
3. **Sheet** — `SheetScreen` populates a `DataTable` row per callable entry from a fixture CSV set.
4. **Teleprompter nav** — `n`/`p`/`b` move the step index and toggle the brief within bounds.
5. **Disposition logging** — driving `m` + selecting a disposition writes an `Outcome` to a temp `Session` file; verify persistence and `stats()`.
6. **Callback** — `c` modal persists a `callback` outcome with `callback_at`.
7. **Shared helpers** — `salescall/callflow.py` `flat_steps` / `DISPOSITIONS` unit tests; assert `console.py` still imports them (classic path intact).
8. Existing pipeline tests remain green.

Target: keep/extend coverage; cockpit screens and shared helpers covered per the 80% guideline.

## Out of scope

- Cockpit demo/sample data.
- Restyling or re-flowing the existing pipeline screens beyond the file move.
- Any change to scraping/emailing/intel logic itself.
- Unrelated refactors outside the files listed above.
