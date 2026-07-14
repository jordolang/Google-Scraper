# Changelog

All notable changes to this project are recorded here. The newest release is at
the top, and every entry is written by `.github/workflows/version.yml` when a
push lands on `main` — so this file is the project's history, not a to-do list.

**How versions move** — a feature advances the number by a tenth (1.0 → 1.1 →
1.2); a fix or small adjustment advances the letter (1.2 → 1.2a → 1.2b → 1.2c).
A feature drops the letters, because the fixes they recorded are now shipped.
The bump is driven by the commit subject: `feat:` is a feature, everything else
(`fix:`, `docs:`, `chore:`, `refactor:`…) is a fix-level change. See
[Versioning](README.md#️-versioning) for the full rules.

## [1.0] - 2026-07-13

The first versioned release. Everything below already existed or landed with it;
from here on, each push writes its own entry.

### Added
- **Every search is saved to `data/`.** Searches and scrapes export to
  `data/<search term>/<location>/listings<date>-<time>.csv` (and
  `contacts<date>-<time>.csv`), so a run is never lost when the TUI closes.
  Shared by the TUI and the CLI scrapers via `data_store.py`; redirect it with
  `GOOGLE_SCRAPER_DATA_DIR`.
- **The listings CSV is the record of a whole campaign.** The search fills in the
  business columns, the website scan folds in `email` / `contact_name` /
  `scraped_phone`, and a delivered email stamps `emailed`, `emailed_at`,
  `emailed_to`, `emailed_subject` and `email_template` onto that business's row.
- **Emailed businesses drop off the call script.** `salescall` skips any listing
  marked `emailed`, so nobody gets cold-called right after being emailed.
- **Phone lookup fallback** (`phone_lookup.py`): when a website scan comes up
  empty, `g` (Google) or `y` (Yellow Pages) on the contacts screen searches a
  directory for the missing number. Results are tagged with `phone_source`,
  exported, shown in the TUI, and picked up by the call script.
- **The workflow's shortcuts are on screen.** Each step prints the key that
  advances it under the list it acts on: `enter` search → `s` scan (or `e` to
  skip it) → `c` compose → `ctrl+s` send → `ctrl+f` finish.
- **Automatic versioning**: `scripts/bump_version.py` plus a GitHub Actions
  workflow that bumps `VERSION`, writes this changelog, and tags each release.
- Interactive Textual TUI for the whole scrape → scan → compose → send flow,
  with a `--demo` mode that needs no browser or credentials.
- Sales Call Cockpit: prioritized, intelligence-driven call queue over the
  scraped data.
- K-12 school sports fundraiser pipeline.
- Google Maps scraper, website contact scraper, email generator, and SMTP sender.
