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

## [1.7b] - 2026-08-23

### Fixed
- reliable Google Maps phone extraction (card harvest + glyph strip)

## [1.7a] - 2026-08-23

### Fixed
- stop the licence-key guard blocking every release

## [1.7] - 2026-08-23

### Added
- payment processing, licensing, and a competitive analysis

### Fixed
- let a build without a licence key still build

## [1.6] - 2026-08-22

### Fixed
- step past taken tags, releasing the macOS builds [feature]

## [1.4] - 2026-08-22

### Added
- bundle Chromium in the exe, and build for ARM64 as well as x64
- ship chromedriver inside the exe so nothing downloads at first run

### Fixed
- hand Selenium the bundled driver instead of letting it look for one
- verify the browser payload in Python, not a bash heredoc
- two phone numbers side by side stay two numbers
- one number per phone, and prove the bundled driver runs
- package selenium whole so the .exe can actually scrape

## [1.3b] - 2026-08-21

### Changed
- publish the Windows .exe on every release

## [1.3a] - 2026-08-21

### Changed
- Create devcontainer with Catnip feature

## [1.3] - 2026-08-21

### Added
- Windows desktop app (PySide6 GUI) packaged as a single .exe

### Fixed
- address review findings across the desktop app
- wait for the packaged .exe self-test instead of racing it

## [1.2] - 2026-08-07

### Added
- preview the composed email in a browser window from the TUI
- load SMTP credentials from a .env file

## [1.1] - 2026-07-27

### Added
- industry-themed dark email templates + in-TUI pricing control

## [1.0a] - 2026-07-14

### Changed
- trigger version workflow (retry, no skip marker)

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
