# 🔍 Google Maps Business Scraper & Email Generator

A comprehensive Python-based toolkit for scraping business information from Google Maps and turning it into personalized outreach — email campaigns *and* a prioritized, intelligence-driven phone-call cockpit. Perfect for local business prospecting, lead generation, and automated email + call campaigns.

[![Version](https://img.shields.io/badge/version-1.0-blueviolet.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Selenium](https://img.shields.io/badge/selenium-4.15+-green.svg)](https://selenium-python.readthedocs.io/)

## 📋 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Interactive Terminal App (TUI)](#-interactive-terminal-app-tui)
  - [Launching the App](#launching-the-app)
  - [The Five Screens](#the-five-screens)
  - [Keyboard Shortcuts](#keyboard-shortcuts)
  - [Built-in Pitch Script](#built-in-pitch-script)
  - [Command-Line Options](#command-line-options)
  - [How It Fits Together](#how-it-fits-together)
- [Windows Desktop App (GUI)](#-windows-desktop-app-gui)
  - [Getting the .exe](#getting-the-exe)
  - [The Screens](#the-screens)
  - [What It Needs](#what-it-needs)
- [Usage — Business Pipeline](#-usage)
  - [Scraping Google Maps](#1-scraping-google-maps)
  - [Scraping Contact Details](#2-scraping-contact-details)
  - [Generating Emails](#3-generating-emails)
  - [Sending Emails](#4-sending-emails)
- [School Fundraiser Pipeline](#-school-fundraiser-pipeline)
  - [Step 1: Discover Schools](#step-1-discover-schools--school_sports_scraperpy)
  - [Step 2: Extract Athletics Contacts](#step-2-extract-athletics-contacts--school_contact_scraperpy)
  - [Step 3: Generate Emails](#step-3-generate-emails--generate_school_emailspy)
  - [Step 4: Send](#step-4-send--send_emailspy-shared)
  - [Supported Sports](#supported-sports-28)
  - [School Configuration](#school-configuration--school_configpy)
  - [Running the Test Suite](#running-the-test-suite)
- [Interactive Terminal App](#️-interactive-terminal-app-all-in-one)
- [Unified Launcher](#-unified-launcher-new)
- [Sales Call Cockpit](#-sales-call-cockpit)
- [Project Components](#-project-components)
- [Output Examples](#-output-examples)
  - [Where It All Lands](#where-it-all-lands)
  - [The Listings CSV](#the-listings-csv--one-file-the-whole-story)
  - [The Contacts CSV](#the-contacts-csv)
- [Data Exports (`data_store.py`)](#-data-exports-data_storepy)
- [Phone Lookup (`phone_lookup.py`)](#️-phone-lookup-phone_lookuppy)
- [Licensing & Pricing](#-licensing--pricing)
- [Versioning](#️-versioning)
- [Configuration](#-configuration)
- [Documentation](#-documentation)
- [Legal & Ethics](#-legal--ethics)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)

## ✨ Features

### 📞 Sales Call Cockpit (New)
- Turn scraped businesses into a **prioritized phone-call campaign** with a live teleprompter
- Four-tier prioritization (no-website/no-email first) ranked by reviews + rating within each tier
- Deep per-business **website intelligence**: PageSpeed / Core Web Vitals, runtime JS & network errors, tech stack, hosting provider & cost, and an SEO audit — each with a spoken sales translation
- **Local SEO ranking** — treats your scrape as the competitive set and computes each business's rank within its field, competitors above it, and closest rival (real Google local-pack positions via SerpApi when a `SERPAPI_KEY` is set, proxy ranking otherwise)
- Live cockpit walks the **OPEN → DISCOVER → PITCH → CLOSE** playbook with SAY / DO / CUE / ANTICIPATE / OPTIONS cues and objection handlers
- Outcomes and callbacks persist to `.salescall_cache/session.json` — pause and resume any time
- See **[SALES_CALL_README.md](docs/SALES_CALL_README.md)** for full documentation

### 🏫 K-12 School Sports Fundraiser Pipeline (New)
- Discover K-12 schools in any US city, state, or district via Google Search
- Filter results to `.k12` and `.edu` domains — no business noise
- Extract athletics directors, coaches, and staff contacts from school websites
- Three extraction strategies handle table-based, card/div-based, and plain-text athletics pages
- Detect the specific sport(s) a contact is associated with (28 supported sports)
- Filter out shared/office emails — personal contacts only
- Generate school-spirit–styled fundraiser emails (green/gold template)
- Sport-specific pitch copy tuned to each program's activity
- Greeting name generation handles "Coach Smith", "Athletic Director", and generic staff
- Subject lines vary deterministically per contact — no identical subject blasts
- Summary output is compatible with the existing `send_emails.py` sender
- **152 automated tests** across config, scraper, contact extraction, and email generation

### 🖥️ Interactive Terminal App (New)
- Run the entire pipeline from one navigable TUI — no juggling scripts or CSVs
- Type a search field + location and see live results in the same window
- Check off the businesses you want, then scan their websites for contacts automatically
- Review found contacts, pick your recipients, and compose/edit each email inline
- Send everything over SMTP from the same screen (with a safe dry-run default)
- Every step's shortcut is spelled out under the list it acts on — see [Moving through the workflow](#-moving-through-the-workflow)
- `--demo` mode tours the whole flow with sample data — no browser or credentials needed

### 💾 Every Search Is Saved (New)
Nothing is scraped and then lost. Each search writes CSVs to a folder named after
what you searched for and where:

```
data/
└── Electricians/
    └── Zanesville-OH/
        ├── listings71326-1109pm.csv    # the search results
        └── contacts71326-1109pm.csv    # what the website scan found
```

The **listings file is the record of the whole campaign**. The search fills in the
business columns, the website scan folds in `email` / `contact_name` /
`scraped_phone`, and a delivered email stamps `emailed`, `emailed_at`,
`emailed_to`, `emailed_subject` and `email_template` onto that business's row.

Two consequences worth knowing:

- **Emailed businesses drop off the call script.** Once a row is marked `emailed`,
  `sales_calls.py` and the cockpit skip it — you don't cold-call someone you just
  emailed. (`load_businesses(..., include_emailed=True)` shows them anyway.)
- **Demo runs are quarantined** under `data/_demo/` and never reach the call queue.

Point the exports somewhere else with `GOOGLE_SCRAPER_DATA_DIR=/path/to/dir`.

### ☎️ Phone Lookup Fallback (New)
Some businesses publish nothing on their website — or have no website at all. When
the contact scan comes up empty, press **`g`** (Google) or **`y`** (Yellow Pages)
on the contacts screen to search a directory for the missing phone number. Anything
found is written to the CSVs (tagged with `phone_source` so you know where it came
from), shown in the TUI, and picked up by the call script.

### 🗺️ Google Maps Scraping
- Extract comprehensive business data from Google Maps search results
- Collect: names, addresses, phone numbers, websites, ratings, reviews, categories
- Configurable headless/visible browser mode
- Automatic scroll pagination for bulk collection
- CSV and JSON export formats

### 📧 Contact Information Scraping
- Intelligent website contact page detection
- Extract emails, phone numbers, and contact names from business websites
- Multiple phone format support (US and international)
- Smart regex patterns with false-positive filtering
- Batch processing of Google Maps results

### 💌 Email Generator
- Generate personalized HTML emails from scraped data
- Beautiful, responsive email templates with gradient designs
- Three-tier pricing packages (Launchpad, Professional, Enterprise)
- Automated email personalization using business names
- Batch email generation with summary reports
- Professional HTML formatting for direct copy-paste into Gmail

### 📤 Automated Email Sender
- Send generated emails automatically via SMTP
- Personalized subject lines for each business
- Intelligent email validation and filtering
- Dry run mode for testing
- Rate limiting and delay configuration
- Detailed sending logs and statistics
- Support for Gmail, Google Workspace, and other providers

### 🛠️ Additional Tools
- CSV to HTML table converter
- HTML to PDF converter
- Automated file organization by timestamp

## 🚀 Quick Start

### Business Outreach Pipeline

Get up and running in under 5 minutes!

```bash
# 1. Clone the repository
git clone https://github.com/jordolang/Google-Scraper.git
cd Google-Scraper

# 2. Install dependencies
pip install -r requirements.txt

# 3. Scrape Google Maps for businesses
python google_maps_scraper.py "plumbers" --location "New York, NY"

# 4. Scrape contact details from websites
python contact_scraper.py google_maps_results_*.csv

# 5. Generate personalized emails
python generate_emails.py

# 6. Send emails automatically
python send_emails.py
```

📖 **See [QUICK_START.md](docs/QUICK_START.md) for detailed step-by-step instructions!**

---

### 🖥️ Interactive Terminal App (All-in-One)

Prefer to do everything from a single guided interface instead of running four
separate scripts? Launch the TUI:

```bash
# Install dependencies (adds Textual for the TUI)
pip install -r requirements.txt

# Explore the full flow with built-in sample data — no browser or SMTP needed
python scraper_tui.py --demo

# Run for real (drives Chrome for scraping and SMTP for sending)
python scraper_tui.py

# Options
python scraper_tui.py --from-email you@yourdomain.com   # sender address
python scraper_tui.py --template email_template.html    # email HTML template
python scraper_tui.py --visible                          # show the browser window
python scraper_tui.py --help                             # all options
```

#### 🧭 Moving through the workflow

Each step is its own screen. The key that advances you to the next one is printed
under the list it acts on (and in the footer), so you never have to hunt for the
way forward. `Esc` always goes back.

| Step | Screen | Advance with | What you do |
|------|--------|--------------|-------------|
| 1 | **Search** | `enter` | Type what to search for (e.g. `electricians`) and a location. Results — and a CSV under `data/` — appear immediately. |
| 2 | **Results** | `s` scan · `e` skip scan | Space-toggle businesses (`a` = all, `n` = none). `s` scans their websites for contacts; `e` skips straight to emailing with the listing data you already have. |
| 3 | **Contacts** | `c` compose | Review what each site gave up; businesses with a usable email are pre-selected. Came up empty? `g` / `y` looks the phone number up on Google / Yellow Pages. |
| 4 | **Compose** | `ctrl+s` | Pick a recipient on the left, edit its subject and message on the right — edits persist as you switch. |
| 5 | **Send** | `ctrl+s` send · `ctrl+f` finish | Enter your app password, keep **Dry run** on for a preview, then send. Progress streams in the log. |

Businesses that were actually emailed are logged on the listings CSV and vanish
from the call script — see [Every Search Is Saved](#-every-search-is-saved-new).

The TUI reuses the exact same scraping, generation, and sending logic as the
standalone scripts — it's a front-end over `google_maps_scraper.py`,
`contact_scraper.py`, `phone_lookup.py`, `generate_emails.py`, and
`send_emails.py`, wired together in `tui/` with exports in `data_store.py`.

> 💡 Gmail / Google Workspace senders need an **App Password**
> (<https://myaccount.google.com/apppasswords>), not your normal password.

---

### 🧭 Unified Launcher (New)

Both terminal UIs — the scrape→email pipeline above and the [Sales Call
Cockpit](docs/SALES_CALL_README.md) — now live under one Textual app:

```bash
python app.py                     # home: pick pipeline or cockpit
python app.py --start cockpit     # straight to the sales-call cockpit
python app.py --demo              # pipeline sample-data mode

# Standalone shims — same underlying app, unchanged entrypoints
python scraper_tui.py             # pipeline shim
python sales_calls.py             # cockpit shim

# Original Rich-terminal cockpit remains available as a fallback
python sales_calls.py --classic {prep|sheet|call}
```

`app.py` opens on a **Home** screen where you pick which tool to use; `Esc`
pops back to Home from either flow. `scraper_tui.py` and `sales_calls.py`
are thin shims — they boot the same unified app straight into their
respective flow, so all existing muscle-memory commands keep working. The
original non-Textual Rich cockpit (see `SALES_CALL_README.md`) is still
available in full via `sales_calls.py --classic`.

---

### 🏫 School Fundraiser Pipeline (New)

Target K-12 athletics programs for Jose Madrid Salsa fundraiser outreach:

```bash
# 1. Discover schools in a city/state
python school_sports_scraper.py --city "Columbus" --state "OH"

# 2. Extract athletics contacts from school websites
python school_contact_scraper.py school_results_*.csv

# 3. Generate personalized fundraiser emails
python generate_school_emails.py

# 4. Send using the shared email sender
python send_emails.py
```

## 📦 Installation

### Prerequisites
- Python 3.7 or higher
- Google Chrome browser
- ChromeDriver (automatically managed by Selenium 4.15+)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/jordolang/Google-Scraper.git
   cd Google-Scraper
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify installation**
   ```bash
   python google_maps_scraper.py --help
   ```

## 🖥️ Interactive Terminal App (TUI)

Instead of running the four scripts by hand and passing CSV files between them,
you can drive the **entire pipeline from one guided terminal interface**. Type
your search, pick the businesses you want, let it scrape their websites for
contacts, edit each email, and send — all without leaving the program.

The TUI is built with [Textual](https://textual.textualize.io/) and reuses the
exact same scraping, generation, and sending logic as the standalone scripts.
The code lives in the `tui/` package. It's part of the [Unified
Launcher](#-unified-launcher-new): `python app.py` opens on a Home screen where
you pick this pipeline or the sales-call cockpit, and `python scraper_tui.py` is
a thin shim that boots straight into the pipeline flow described here.

### Launching the App

```bash
# Install dependencies (adds Textual for the TUI)
pip install -r requirements.txt

# Explore the whole flow with built-in sample data —
# no browser, network, or SMTP credentials required
python scraper_tui.py --demo        # or: python app.py --demo --start pipeline

# Run for real (drives Chrome for scraping and SMTP for sending)
python scraper_tui.py               # or: python app.py  → pick "Pipeline" on Home
```

> 💡 **Try `--demo` first.** It walks you through every screen using canned
> sample data so you can learn the interface before pointing it at live
> Google Maps searches and your real inbox.

### The Five Screens

Each step is its own screen. The key that advances you to the next one is printed
under the list it acts on (and in the footer), so the way forward is never
something you have to hunt for. `Esc` takes you back.

| # | Screen | Advance with | What you do |
|---|--------|--------------|-------------|
| 1 | **🔍 Search** | `enter` | Type what to search for (e.g. `electricians`) and a location (e.g. `Zanesville, OH`). Optionally tick *Show browser window*. Results stream into the log — and straight into `data/<term>/<location>/listings*.csv`. |
| 2 | **✅ Results** | `s` scan · `e` skip scan | A checkable list of every business found. Toggle rows with **Space** (`a` = all, `n` = clear). `s` scans the selected websites for contacts; `e` skips the scan and takes the listing data straight to the email step. |
| 3 | **📇 Contacts** | `c` compose | What each website gave up: emails, contact names, phone numbers. Businesses with a usable email are pre-selected; ones already emailed are flagged and deselected. Websites that gave up nothing? `g` / `y` looks their phone number up on Google / Yellow Pages. |
| 4 | **✉️ Compose** | `ctrl+s` | Recipients on the left; select one to load its **To**, **Subject**, and **Message (HTML)** on the right. Edits are saved as you switch between recipients. |
| 5 | **🚀 Send** | `ctrl+s` send · `ctrl+f` finish | Enter your email account's app password. Leave **Dry run** enabled for a safe preview, or turn it off to deliver. Everything actually sent is logged onto the listings CSV and drops off the call script. |

### Keyboard Shortcuts

The workflow keys — each is also printed under the list it applies to:

| Key | Action | Screen |
|-----|--------|--------|
| `enter` | Run the search | Search |
| `s` | Scan the selected websites for contacts | Results |
| `e` | Skip the scan; go straight to composing emails | Results |
| `g` | Look missing phone numbers up on **Google** | Contacts |
| `y` | Look missing phone numbers up on **Yellow Pages** | Contacts |
| `c` | Compose emails for the selected businesses | Contacts |
| `Ctrl+S` | Send the composed emails | Compose / Send |
| `Ctrl+F` | Finish the campaign and see the summary | Send |

And the usual navigation:

| Key | Action |
|-----|--------|
| `Space` | Toggle the highlighted row in a selection list |
| `a` | Select all (Results / Contacts screens) |
| `n` | Clear selection (Results / Contacts screens) |
| `↑` / `↓` | Move between rows / recipients |
| `Tab` | Move focus between fields and buttons |
| `Esc` | Go back to the previous screen |
| `Ctrl+G` | Open/close the **Pitch Script** guide (from any screen) |
| `Ctrl+C` | Quit the app |
| `Ctrl+P` | Open the command palette |

> Compose and Send use `Ctrl+S` rather than a letter key because a bare `s` would
> be swallowed by the subject, body, and password fields.

### Built-in Pitch Script

Press **Ctrl+G** on any screen to pop open a scrollable **Website Pitch Script**
— a step-by-step walkthrough of what to say when you contact a business to pitch
them a website (opening lines, the hook, discovery questions, the offer and
pricing, objection handling, closing, and voicemail/gatekeeper wording). It has
a table-of-contents sidebar for jumping between sections, and **Esc** closes it.

Because it's meant to reach for during a live call, it's available everywhere in
the unified app — on any pipeline screen **and** in the sales-call cockpit — so
you never have to leave the program. The content is read from an editable
Markdown file, **`pitch_script.md`** in the project root, so you can rewrite any
of the wording to match your own voice; the app picks up your edits the next
time you open the guide.

### Command-Line Options

```bash
python scraper_tui.py --help
```

| Option | Description | Default |
|--------|-------------|---------|
| `--demo` | Use built-in sample data — no browser, network, or credentials | Off |
| `--from-email` | Sender email address (also selects the SMTP server) | `jordan@jlang.dev` |
| `--template` | Path to the HTML email template | `email_template.html` |
| `--visible` | Run the scraper browser in visible (non-headless) mode | Off (headless) |

> 💡 Gmail / Google Workspace senders need an
> **[App Password](https://myaccount.google.com/apppasswords)**, not their
> normal account password.

### How It Fits Together

The TUI is a thin front-end — it doesn't reimplement any scraping or sending
logic:

| Pipeline step | Backed by |
|---------------|-----------|
| Search businesses | `google_maps_scraper.py` → `GoogleMapsScraper` |
| Scan websites for contacts | `contact_scraper.py` → `ContactScraper` |
| Build each email from the template | `generate_emails.py` → `EmailGenerator` |
| Send over SMTP | `send_emails.py` → `EmailSender` |

The `tui/` package wires these together:

- **`tui/models.py`** — `Business` and `EmailMessage` dataclasses shared across screens.
- **`tui/pipeline.py`** — adapts the four tools behind coarse `search → scrape → build → send` steps with streaming progress. Selenium/SMTP are imported lazily, and a `DemoPipeline` supplies the `--demo` sample data.
- **`tui/pipeline_screens.py`** — the five pipeline screens (Search, Results, Contacts, Compose, Send). Blocking browser/SMTP calls run in worker threads so the interface never freezes.
- **`tui/app.py`** — the unified `OutreachApp` that hosts the pipeline and cockpit flows, plus the global Ctrl+G pitch-script overlay.
- **`tui/pitch_script.py`** — loads the pitch-script guide from the editable `pitch_script.md` (with a built-in fallback).

Because it shares the underlying tools, anything you send from the TUI behaves
identically to the command-line workflow described below.

---

## 🪟 Windows Desktop App (GUI)

A point-and-click Windows front end over the same pipeline the TUI drives —
one navigation rail, one screen per stage, and a single `.exe` that needs no
Python on the machine it runs on. Full guide: **[docs/WINDOWS_APP.md](docs/WINDOWS_APP.md)**.

```bash
pip install -r requirements.txt -r requirements-gui.txt
python -m gui              # run it
python -m gui --demo       # tour it with sample data — no Chrome, no SMTP
```

### Getting the .exe

| How | What you do |
| --- | --- |
| **Download** | [**Releases**](https://github.com/jordolang/Google-Scraper/releases/latest) → `LocalLeadScraperPro.exe`. Every version bump on `main` publishes one. For an unreleased build, GitHub **Actions → Windows App →** newest run → the `LocalLeadScraperPro-windows` artifact. |
| **What's inside** | Everything: Python, PySide6, Selenium, the scrapers, the templates, **and a Chromium browser with its matching driver**. Nothing to install, nothing downloaded ([how](docs/WINDOWS_APP.md#how-the-browser-rides-along)). |
| **Builds** | Windows: `LocalLeadScraperPro-x64.exe` (Intel/AMD) and `-arm64.exe` (Snapdragon/ARM). macOS: `LocalLeadScraperPro-macos-apple-silicon.zip` (M1+) and `-macos-intel.zip`. All four are built natively and published on every release. |
| **First run on a Mac** | The app is unsigned, so right-click → **Open** the first time rather than double-clicking ([why](docs/WINDOWS_APP.md#the-mac-builds)). |
| **Build it** | On Windows: `packaging\build_windows.bat` → `dist\LocalLeadScraperPro.exe` |
| **From source** | `python -m gui` on any OS |

The executable is self-contained (Python and Qt travel with it), so there is
nothing to install and nothing lands in `Program Files`. PyInstaller cannot
cross-compile, which is why the Windows binary is built by the
[`windows-build`](.github/workflows/windows-build.yml) CI job on a Windows
runner.

### The Screens

| Screen | What it does |
| --- | --- |
| **Dashboard** | Location + one or more industries (`Roofing Contractors, Plumbers`), radius, per-industry result cap. One results tab per industry, with live progress and a tick box per business. |
| **Website Scraper** | Visits each selected site: activity log, progress overview (completed / in flight / remaining / data points / elapsed), and per-category counts — services, images, social profiles, reviews, certifications, hours. Pause and Stop work mid-run. |
| **Business Listings** | The raw listings and the extracted contact data, searchable and filterable (has email, missing contact info, scanned, emailed), paginated, exportable to CSV **or Excel**. |
| **Contacts & Outreach** | Campaign setup (template, subject, delay, daily cap), a recipients grid, browser preview of the composed email, dry-run sending, live counters — plus a **Call Scripts** tab with the pitch script step by step and objection handling personalised per business. |
| **Settings / Tools / Logs / Help** | SMTP account with a Test Connection button, headless or visible Chrome, demo mode, export folder; phone-number lookup, package pricing, re-loading a previous export; a filterable session log; and an in-app guide. |

The GUI writes the same CSVs, into the same `data/<term>/<location>/` folders,
as the terminal app — the two front ends share `tui/pipeline.py`.

### What It Needs

* **Demo mode:** nothing at all.
* **Live scraping:** Google Chrome installed (Selenium drives your own browser).
* **Sending email:** an app-specific password, entered on the Settings page or
  set as `EMAIL_PASSWORD` in a `.env` file. It is never written to disk by the app.

Packaged runs keep exports, editable templates, `pitch_script.md` and
`pricing.json` under `%LOCALAPPDATA%\LocalLeadScraperPro\`; preferences live in
`%APPDATA%\LocalLeadScraperPro\settings.json`.

> Two things the app deliberately does not pretend to do: email **opens, clicks
> and replies are not tracked** (direct SMTP cannot report them), and the
> **radius** control is advisory — Google Maps ranks by proximity to the
> location you type and has no radius filter.

---

## 📖 Usage

### 1. Scraping Google Maps

#### Basic Usage
```bash
# Search for businesses in a specific location
python google_maps_scraper.py "restaurants" --location "San Francisco, CA"

# Coffee shops in Boston
python google_maps_scraper.py "coffee shops" --location "Boston, MA"

# Local gyms
python google_maps_scraper.py "gyms" --location "Chicago, IL"
```

#### Advanced Options
```bash
# Custom output filename
python google_maps_scraper.py "dentists" --location "Los Angeles" --filename dental_leads

# Export to JSON format
python google_maps_scraper.py "plumbers" --location "Seattle" --output json

# Export to both CSV and JSON
python google_maps_scraper.py "electricians" --location "Portland" --output both

# Visible browser mode (debugging)
python google_maps_scraper.py "hotels" --location "Miami" --visible

# Increase scroll depth for more results
python google_maps_scraper.py "contractors" --location "Austin" --max-scrolls 20
```

#### Command-Line Arguments
| Argument | Required | Description | Default |
|----------|----------|-------------|---------|
| `search_term` | Yes | What to search for (e.g., "restaurants") | - |
| `--location` | No | Location to search in | - |
| `--output` | No | Output format: `csv`, `json`, or `both` | `csv` |
| `--filename` | No | Custom output filename (no extension) | Auto-generated |
| `--visible` | No | Run browser in visible mode | False |
| `--max-scrolls` | No | Maximum scrolls to load results | 10 |
| `--friendly-headers` | No | Write `Business Name`-style CSV headers | False |

#### Output Fields
The scraper collects the following data for each business:

| Column | Header with `--friendly-headers` | What it holds |
|--------|----------------------------------|---------------|
| `name` | Business Name | Business name |
| `rating` | Rating | Star rating (e.g. "4.5") |
| `reviews_count` | Reviews Count | Number of reviews |
| `category` | Category | Business category/type |
| `address` | Address | Full address |
| `phone` | Phone | Phone number |
| `website` | Website | Business website URL |
| `plus_code` | Plus Code | Google Plus Code location |
| `hours` | Hours | Operating hours |
| `url` | URL | Google Maps URL |
| `search_term` | Search Term | The search that found it |
| `search_location` | Search Location | Where that search was run |

Each of those is read from two places and merged: the search-result card in
the left-hand feed, and the place detail page. The detail panel routinely
hydrates only halfway, so the card is what keeps the columns full when it
does — and every column has more than one selector behind it, because Maps'
class names change without notice.

**Plus Code** is the one column Google itself sometimes withholds: listings
with a precise street address often render no "Plus code" row at all. A plus
code is a pure function of the coordinates, and those are in the place URL, so
the scraper computes the code when the row is missing. The computed value is
the full global code (`8FVC2222+22`) rather than the shorter locality-relative
form Maps displays (`2222+22 Zurich`); both name the same square, and the
global one needs no locality column to be unambiguous.

The run finishes with a per-column fill rate, so a Maps redesign that empties
a column shows up in the same terminal that ran the scrape:

```
Field coverage across 42 businesses:
  name             42/42  (100.0%)
  rating           41/42  ( 97.6%)
  reviews_count    41/42  ( 97.6%)
  category         42/42  (100.0%)
  address          42/42  (100.0%)
  phone            38/42  ( 90.5%)
  website          31/42  ( 73.8%)   ← low
  plus_code        42/42  (100.0%)
  hours            40/42  ( 95.2%)
  url              42/42  (100.0%)
```

#### Mail-merge headers

Add `--friendly-headers` to write `Business Name,Rating,Reviews Count,…`
instead of the snake_case field names, for a tool that maps columns by their
display name:

```bash
python google_maps_scraper.py "electricians" --location "Zanesville, OH" --friendly-headers
```

The columns and their order are identical either way, and every part of this
app reads both spellings — so a friendly-header export still feeds the contact
scan, the email generator and the call sheet.

### 2. Scraping Contact Details

Extract detailed contact information from business websites:

```bash
# Process the most recent Google Maps CSV
python contact_scraper.py google_maps_results_20251119_060637.csv

# Specify custom output filename
python contact_scraper.py google_maps_results.csv --output my_contacts

# Run with visible browser (debugging)
python contact_scraper.py results.csv --visible

# Export to JSON
python contact_scraper.py results.csv --format json
```

#### What It Extracts
- **Emails**: All valid email addresses found on the website
- **Phone Numbers**: Additional phone numbers beyond Google Maps data
- **Contact Names**: Owner, manager, or contact person names
- **Contact Page URLs**: Direct links to contact pages

### 3. Generating Emails

Generate beautiful, personalized HTML emails from your contact data:

```bash
# Generate emails from the most recent contact CSV
python generate_emails.py

# The script automatically:
# - Finds your most recent CSV file
# - Generates personalized emails
# - Saves them in generated_emails/ folder
# - Creates a summary report
```

#### Email Features
- **Professional Design**: Gradient backgrounds, modern styling
- **Responsive Layout**: Mobile-friendly HTML templates
- **Three Pricing Tiers**:
  - 🚀 **Launchpad**: $499 - Basic website package
  - 💼 **Professional**: $1,499+ - Full custom website
  - 🏢 **Enterprise**: Custom - Complete solution
- **Personalization**: Automatically inserts business names
- **Call-to-Action**: Links to exclusive pricing page

#### Customization
Edit `email_config.py` to customize:
```python
FROM_EMAIL = "your@email.com"
FROM_NAME = "Your Name"
SUBJECT_LINE = "Your Custom Subject"
```

Edit `email_template.html` to change:
- Pricing amounts
- Service descriptions
- Colors and branding
- Footer information

### 4. Sending Emails

Automatically send generated emails via SMTP:

```bash
# Run the email sender (interactive mode)
python send_emails.py

# The script will guide you through:
# 1. Select mode (dry run, send all, or limited batch)
# 2. Configure delay between emails
# 3. Optional skip list
# 4. Enter email password (use App Password for Gmail)
```

#### Sending Modes

**1. Dry Run (Preview)**
- Preview emails without sending
- See recipients and subject lines
- Test your configuration

**2. Send All Emails**
- Send all valid emails in `generated_emails/`
- Automatically filters invalid addresses
- Creates detailed log file

**3. Send Limited Batch (Test)**
- Send a specified number of emails
- Perfect for testing
- Example: Send first 5 emails

#### Features
- **Personalized Subject Lines**: Each business gets a unique subject
- **Email Validation**: Filters out invalid/placeholder emails
- **Rate Limiting**: Configurable delay between sends
- **Sending Logs**: Detailed logs of all sent emails
- **Error Handling**: Graceful handling of failures
- **SMTP Auto-Detection**: Works with Gmail, Google Workspace, Outlook, etc.

#### Gmail/Google Workspace Setup

**Important**: Use an App Password, not your regular password!

1. Enable 2-Factor Authentication
2. Visit: https://myaccount.google.com/apppasswords
3. Generate an App Password
4. Use this password when prompted by the script

**See [EMAIL_SENDER_README.md](docs/EMAIL_SENDER_README.md) for complete documentation!**

## 🗂️ Project Components

```
Google-Scraper/
├── 🧭 app.py                      # Unified launcher (pipeline + cockpit)
├── 📄 scraper_tui.py              # Pipeline TUI shim
├── 📄 sales_calls.py              # Sales Call Cockpit entry point / shim
│
├── 📄 google_maps_scraper.py      # Main Google Maps scraper
├── 📄 contact_scraper.py          # Website contact scraper
├── ☎️ phone_lookup.py             # Google / Yellow Pages phone fallback
├── 💾 data_store.py               # data/ layout, CSV exports, outreach log
├── 📄 generate_emails.py          # Email generator
├── 📄 send_emails.py              # Automated email sender (shared)
├── 📄 email_template.html         # HTML email template (business)
├── 📄 email_config.py             # Email configuration
│
├── 📁 data/                       # Every search, saved (git-ignored)
│   └── <search term>/<location>/  #   listings*.csv + contacts*.csv
│
├── 🖥️ app.py                      # Unified TUI launcher (home → pipeline/cockpit)
├── 🖥️ scraper_tui.py              # Shim: boot straight into the pipeline flow
├── 🖥️ sales_calls.py              # Shim: boot straight into the sales-call cockpit
├── 📁 tui/                        # Terminal app package
│   ├── app.py                     #   Unified OutreachApp + Ctrl+G pitch overlay
│   ├── home.py                    #   Home screen (pick pipeline or cockpit)
│   ├── pipeline_screens.py        #   Search/Results/Contacts/Compose/Send screens
│   ├── pipeline.py                #   Adapts the scripts + demo data
│   ├── pitch_script.py            #   Loads the in-app pitch guide
│   ├── cockpit/                   #   Sales-call cockpit screens
│   └── models.py                  #   Business / EmailMessage dataclasses
├── 📁 salescall/                  # Sales-call cockpit engine (playbook, intel)
├── 📞 pitch_script.md             # Editable website pitch script (Ctrl+G)
│
├── 🏫 school_sports_scraper.py    # K-12 school athletics scraper
├── 🏫 school_contact_scraper.py   # School website contact extractor
├── 🏫 generate_school_emails.py   # School fundraiser email generator
├── 🏫 school_email_template.html  # School fundraiser HTML template
├── 🏫 school_config.py            # School pipeline configuration
├── 🏫 ohio_district_loader.py     # Bulk Ohio school-district loader
│
├── 📞 salescall/                  # Sales Call Cockpit engine
│   ├── models.py                  #   dataclasses (Business, WebsiteIntel, …)
│   ├── data_loader.py             #   merge scrape + contact CSVs → records
│   ├── prioritize.py              #   tiering + scoring + call durations
│   ├── intel/                     #   website analysis (pagespeed, seo, techstack, hosting, errors)
│   ├── localseo.py / serp.py      #   local-pack ranking (proxy + real SERP)
│   ├── playbook.py / objections.py#   staged call script + objection handlers
│   ├── console.py / callflow.py   #   interactive cockpit + call flow
│   └── scheduler.py / cache.py    #   session + intel persistence
│
├── 🖥️ tui/                        # Textual UI (unified app)
│   ├── app.py / home.py           #   launcher shell + home screen
│   ├── pipeline*.py               #   scrape → email pipeline screens
│   └── cockpit/                   #   sales-call cockpit screens
│
├── 📄 csv_to_table.py             # CSV to HTML converter
├── 📄 html_to_pdf.py              # HTML to PDF converter
├── 📄 requirements.txt            # Python dependencies
├── 📄 README.md                   # This file
│
├── 🏷️ VERSION                     # Current version (e.g. 1.0)
├── 🏷️ CHANGELOG.md                # Written automatically on every push
├── 📁 scripts/
│   └── bump_version.py            #   The versioning scheme (feature = .1, fix = letter)
├── 📁 .github/workflows/
│   └── version.yml                #   Bumps, changelogs, and tags each push to main
│
├── 📁 docs/                       # Quick start, pricing, offers, sender/generator guides
│
├── 📁 tests/                      # Test suite
│   ├── test_data_store.py         #   data/ exports, outreach log, call-script exclusion
│   ├── test_phone_lookup.py       #   Google / Yellow Pages phone fallback
│   ├── test_bump_version.py       #   the versioning scheme
│   ├── test_school_*.py           #   school pipeline
│   ├── test_cockpit_*.py          #   sales-call cockpit screens
│   ├── test_callflow.py           #   call flow
│   ├── test_tui.py / test_home.py #   pipeline TUI + launcher
│   └── test_entrypoints.py        #   app.py / shim re-exports
│
└── 📁 generated_emails/           # Output directory
```

## 📊 Output Examples

### Where It All Lands

A search for `electricians` in `Zanesville, OH` writes:

```
data/Electricians/Zanesville-OH/
├── listings71326-1109pm.csv    # the search results — and the campaign's record
└── contacts71326-1109pm.csv    # what the website scan (or a phone lookup) found
```

### The Listings CSV — one file, the whole story

**File**: `data/Electricians/Zanesville-OH/listings71326-1109pm.csv`

This is the file to open if you only open one. Three stages write to it:

| Written by | Columns |
|------------|---------|
| **The search** | `name`, `rating`, `reviews_count`, `category`, `address`, `phone`, `website`, `plus_code`, `hours`, `url`, `search_term`, `search_location` |
| **The website scan** *(or the phone lookup)* | `email`, `contact_name`, `scraped_phone`, `phone_source` |
| **A delivered email** | `emailed`, `emailed_at`, `emailed_to`, `emailed_subject`, `email_template` |

```csv
name,rating,category,address,phone,website,email,contact_name,scraped_phone,phone_source,emailed,emailed_at,emailed_to,email_template
"Bright Spark Electric","4.8","Electrician","123 Main St, Zanesville, OH","(614) 555-0142","https://brightspark.example","info@brightspark.example","Dana Rivera","(614) 555-0142","","yes","2026-07-13 23:31:23","info@brightspark.example","standard contact email"
"Reliable Circuit Pros","5.0","Electrician","9 Pine St, Zanesville, OH","","","","","(614) 555-0101","yellowpages","","","",""
```

Read that second row: no website, so the scan found nothing — the number came
from a Yellow Pages lookup (`phone_source`), and it's still callable. The first
row was emailed, so the call script will skip it from now on.

- `phone_source` is empty when the number came off the business's own website;
  `google` or `yellowpages` when a directory search found it.
- `emailed` is `yes` only for mail that was **actually delivered** — a dry run
  never marks anyone.

### The Contacts CSV

**File**: `data/Electricians/Zanesville-OH/contacts71326-1109pm.csv`

Every listing column, carried through untouched, plus what the website scan
found and the phone-source provenance. It is a superset of the listings CSV,
not a subset of it — so a mail merge pointed at either file has the same
fields to map:

```csv
name,rating,reviews_count,category,address,phone,website,plus_code,hours,url,search_term,search_location,email,contact_name,scraped_phone,phone_source,emailed,emailed_at,emailed_to,emailed_subject,email_template,original_phone
"Bright Spark Electric","4.8","127","Electrician","123 Main St, Zanesville, OH","(614) 555-0142","https://brightspark.example","86FXW2P3+9M","Mon: 8 AM-5 PM; Tue: 8 AM-5 PM","https://maps.google.com/...","Electricians","Zanesville, OH","info@brightspark.example","Dana Rivera","(614) 555-0142","","","","","","","(614) 555-0142"
```

`original_phone` is the number Google Maps gave us, kept beside the one the
website gave us. `--friendly-headers` works here too.

### Email Generator Output
**File**: `generated_emails/joes_pizza_email.html`

Beautiful HTML email with:
- Personalized greeting: "Hi Joe's Pizza Team,"
- Professional service offerings
- Three-tier pricing structure
- Call-to-action buttons
- Contact information
- Responsive design

---

## 🏫 School Fundraiser Pipeline

This pipeline targets K-12 athletics programs for Jose Madrid Salsa fundraiser outreach — coaches, athletic directors, and booster staff. Schools earn **50% profit** with zero upfront cost, making this an easy pitch to any program that needs equipment, uniforms, or travel funds.

### Pipeline Overview

```
school_sports_scraper.py  →  school_contact_scraper.py  →  generate_school_emails.py  →  send_emails.py
        (discover)                    (extract contacts)           (build emails)              (send)
```

---

### Step 1: Discover Schools — `school_sports_scraper.py`

Searches Google for K-12 schools in your target area and filters results to verified school domains.

```bash
# Search by city and state
python school_sports_scraper.py --city "Columbus" --state "OH"

# Search by school district name
python school_sports_scraper.py --district "Columbus City Schools" --state "OH"

# Limit results
python school_sports_scraper.py --city "Cleveland" --state "OH" --max-results 50

# Run with visible browser for debugging
python school_sports_scraper.py --city "Dayton" --state "OH" --visible
```

**Output**: `school_results_YYYYMMDD_HHMMSS.csv`

**Output Fields**:
| Field | Description |
|-------|-------------|
| `school_name` | School name extracted from search result |
| `url` | School website URL (.k12 or .edu domain) |
| `district` | School district if detectable |
| `city` | Target city |
| `state` | Target state |
| `search_query` | Which query template found this result |

**Domain Filtering**: Only results matching `.k12`, `.edu`, or known school CMS domains (Finalsite, Edlio, SchoolPointe, Blackboard, etc.) are kept.

---

### Step 2: Extract Athletics Contacts — `school_contact_scraper.py`

Visits each school website, finds the athletics section, and extracts coaching/staff contacts.

```bash
# Process the most recent school results CSV
python school_contact_scraper.py school_results_20260321_164340.csv

# Specify output filename
python school_contact_scraper.py school_results.csv --output my_contacts

# Visible browser for debugging
python school_contact_scraper.py school_results.csv --visible
```

**Output**: `school_contacts_YYYYMMDD_HHMMSS.csv`

**Three Extraction Strategies** (tried in order):
1. **Table format** — Staff directories laid out in `<table>` rows
2. **Card/div format** — Modern card-based layouts (`.staff-card`, `.coach-card`, etc.)
3. **Text block format** — Plain paragraph/list content with regex matching

**Output Fields**:
| Field | Description |
|-------|-------------|
| `school_name` | School name |
| `contact_name` | Staff member's name |
| `title` | Job title (e.g., "Athletic Director", "Head Football Coach") |
| `email` | Personal/work email address |
| `sport` | Detected sport (from URL, heading, or context) |
| `url` | School website URL |
| `district` | District name |
| `city` | City |
| `state` | State |

**Personal Email Filtering**: Shared emails like `info@`, `office@`, `admin@` are excluded — only personal staff contacts are captured.

---

### Step 3: Generate Emails — `generate_school_emails.py`

Builds personalized HTML fundraiser emails from the contacts CSV.

```bash
# Generate from most recent contacts CSV
python generate_school_emails.py

# Specify input file
python generate_school_emails.py --input school_contacts_20260321_170000.csv
```

**Output**: `generated_school_emails/` directory containing one HTML file per contact, plus a `summary.csv` compatible with `send_emails.py`.

**Personalization Features**:
- **Greeting names**: Generates "Coach Smith", "Athletic Director Johnson", or "Coaching Staff" based on name/title data
- **Sport-specific pitches**: Each of the 28 supported sports has a tailored pitch paragraph explaining why salsa fundraising fits their program
- **Subject line variation**: 6 subject line templates, selected deterministically per contact — no two identical subjects in the same batch
- **Template variables replaced**: `{{CONTACT_NAME}}`, `{{SPORT}}`, `{{SCHOOL_NAME}}`, `{{SPORT_PITCH}}`, `{{FUNDRAISER_PERCENTAGE}}` (50%), `{{CTA_URL}}`, `{{FROM_NAME}}`, `{{FROM_EMAIL}}`

**School Email Template** (`school_email_template.html`):
- Green/gold school-spirit color scheme
- Showcases Jose Madrid Salsa product line
- Prominently highlights 50% profit and zero upfront cost
- 3-step CTA: Browse → Share → Earn
- Links to `josemadridsalsa.com`

---

### Step 4: Send — `send_emails.py` (shared)

The same sender used for the business pipeline works for school emails.

```bash
python send_emails.py
# When prompted, point it to generated_school_emails/summary.csv
```

---

### Supported Sports (28)

| | | | |
|---|---|---|---|
| Football | Basketball | Baseball | Softball |
| Soccer | Volleyball | Track & Field | Cross Country |
| Wrestling | Swimming | Tennis | Golf |
| Lacrosse | Field Hockey | Cheerleading | Gymnastics |
| Hockey | Water Polo | Bowling | Rugby |
| Dance | Drill Team | Powerlifting | Archery |
| Fencing | Rowing | Badminton | Table Tennis |

---

### School Configuration — `school_config.py`

All school pipeline settings live in `school_config.py`:

```python
# Fundraiser terms
FUNDRAISER_CONFIG = {
    "fundraiser_percentage": "50%",          # Profit split shown in emails
    "product_url": "https://josemadridsalsa.com",
}

# Your sender info
FROM_EMAIL = "jordan@jlang.dev"
FROM_NAME  = "Jordan Lang"

# Search behavior
MAX_SEARCH_PAGES     = 3    # Google result pages per query
MAX_QUERIES_PER_TARGET = 5  # Query templates tried per city/district

# Output paths
TEMPLATE_PATH = "school_email_template.html"
OUTPUT_DIR    = "generated_school_emails"
```

**To retarget for a different product/brand**, only `school_config.py` and `school_email_template.html` need updating — the scraper and contact extractor are brand-agnostic.

---

### Running the Test Suite

```bash
# Run the full suite (187 tests: school pipeline, cockpit, and TUI)
python -m pytest tests/ -v

# Run just the school pipeline (152 tests)
python -m pytest tests/test_school_config.py -v
python -m pytest tests/test_school_sports_scraper.py -v
python -m pytest tests/test_school_contact_scraper.py -v
python -m pytest tests/test_generate_school_emails.py -v
```

School-pipeline coverage includes: config validation, search query generation, domain filtering, all three contact extraction strategies, sport detection, greeting name generation, subject line variation, email template rendering, and CSV output format. The remaining tests cover the Sales Call Cockpit (call flow, screens), the pipeline TUI, and the unified launcher entrypoints.

---

## 📞 Sales Call Cockpit

Once you've scraped businesses, turn them into a **prioritized phone-call campaign**
with deep per-business website intelligence and a live, interactive teleprompter.

```bash
# (Optional) free Google PageSpeed key for reliable speed scores in batch
export PAGESPEED_API_KEY="your-key"

# 1. Analyze + cache every business's website (run once per scrape)
python sales_calls.py prep

# 2. See the prioritized call schedule
python sales_calls.py sheet

# 3. Start calling — the live cockpit
python sales_calls.py call
```

Run `python sales_calls.py` with no arguments for the interactive Textual cockpit
(the classic Rich-terminal commands above stay available via `--classic`).

**How it prioritizes** — Tier 1 (no website *and* no email) → Tier 2 (no website) →
Tier 3 (weak site / no contact) → Tier 4 (established site), with businesses ranked
by reviews + rating inside each tier. Businesses with no valid phone are parked.

**What the intel gathers** (`salescall/intel/`) — PageSpeed / Core Web Vitals,
runtime JS & network errors (headless Chrome), tech stack, hosting provider + cost,
and a full SEO audit. Every finding carries a spoken sales translation.

**Local SEO ranking** (`salescall/localseo.py`, `salescall/serp.py`) — your scrape
is the competitive set, so each business gets a local rank within its field,
competitors above it, and its closest rival. Set `SERPAPI_KEY` in `.env` for real
Google local-pack positions; otherwise a proximity + prominence proxy is used.

Full details, controls, and architecture live in
**[SALES_CALL_README.md](docs/SALES_CALL_README.md)**.

---

## 💾 Data Exports (`data_store.py`)

Every scrape and search goes through this module, so the TUI, the CLI scrapers,
and the call script all agree on where data lives and what the columns mean.

| Function | What it does |
|----------|--------------|
| `data_root()` | The `data/` directory exports live under. `GOOGLE_SCRAPER_DATA_DIR` overrides it. |
| `slugify(value)` | One safe path segment: `"Zanesville, OH"` → `Zanesville-OH`. The state is kept, so two same-named cities never merge. |
| `search_dir(term, location)` | Creates and returns `data/<term>/<location>/`. |
| `timestamped_name(prefix)` | `listings71326-1109pm.csv` — month, day, year, then the clock time. |
| `export_listings(rows, term, location)` | Writes the search results. Returns the path, or `None` if there was nothing to save. |
| `export_contacts(rows, term, location)` | Writes the website-scan results. |
| `update_listings(path, updates)` | Merges contact info and outreach into an existing listings CSV, keyed by business name. This is what keeps one file current instead of leaving a stale snapshot of step one. |
| `outreach_record(to, subject)` | The columns stamped on a listing when its email is delivered — including `email_template` = *standard contact email*. |
| `was_emailed(row)` | Whether a listings row records a delivered email. The call script uses this to skip it. |
| `LISTING_FIELDS` / `CONTACT_FIELDS` | The column order of each CSV. |

Two invariants worth relying on: an export is written in a `finally`, so a scan
that dies half way still saves what it got; and a second export in the same
minute gets a `-2` suffix rather than clobbering the first.

```python
import data_store

path = data_store.export_listings(rows, "Electricians", "Zanesville, OH")
data_store.update_listings(path, {
    data_store.row_key("Bright Spark Electric"):
        data_store.outreach_record("info@brightspark.example", "Your website"),
})
```

## ☎️ Phone Lookup (`phone_lookup.py`)

The fallback for businesses that publish nothing — or have no website at all.

| Function | What it does |
|----------|--------------|
| `PhoneLookup(headless=True)` | Opens a browser for directory searches. Usable as a context manager. |
| `.google(name, location)` | Phone numbers off a Google results page (knowledge panel included). |
| `.yellowpages(name, location)` | Phone numbers from a Yellow Pages search — prefers the listing's phone element over a blind text scrape, so it can't grab a neighbouring business's number. |
| `.find(name, location, sources)` | Tries each source in turn; returns `{"phones": [...], "source": "google"}`. |
| `normalize(text)` / `extract_phones(text)` | The parsing, on its own: formats to `(614) 555-0142`, drops placeholders like `111-111-1111`, and skips toll-free numbers. |

```python
from phone_lookup import PhoneLookup

with PhoneLookup() as lookup:
    lookup.find("Bright Spark Electric", "Zanesville, OH")
    # {'phones': ['(614) 555-0142'], 'source': 'google'}
```

In the TUI this is the `g` / `y` action on the contacts screen; it runs against
every business whose website scan came up empty, and what it finds flows into the
CSVs (tagged `phone_source`), the list on screen, and the call script.

## 🔑 Licensing & Pricing

The app is sold two ways, at three tiers, with a 72-hour trial. Full detail in
**[docs/PRICING.md](docs/PRICING.md)**; the design and the operator runbook are in
**[docs/LICENSING.md](docs/LICENSING.md)**.

| | Solo | Pro | Agency |
|---|---|---|---|
| Monthly | $39 | $89 | $199 |
| Yearly | $390 | $890 | $1,990 |
| One-time (never expires, 12 months of updates) | $599 | $1,299 | $2,999 |
| Machines | 2 | 3 | 10 |

**Subscription** keeps renewing and always has the newest version.
**Perpetual** is paid once, never expires, and includes twelve months of
updates — after that it keeps working, it just stops changing.

The **72-hour trial** unlocks every feature; searches cap at 25 results and
email sending stays in dry-run.

### From the app

The desktop app has a **Licence** screen: activate a key, start the trial, see
what your plan covers, buy or upgrade, and hand a computer's seat back.

### From the terminal

```bash
python app.py --licence status       # what this computer is running
python app.py --licence plans        # the price list
python app.py --licence trial        # start the free 72 hours
python app.py --licence activate LLSP-XXXXX-XXXXX-XXXXX-XXXXX
python app.py --licence deactivate   # free this computer's seat
```

### How it behaves

- **Offline-first.** Licences are Ed25519-signed and verified on your machine.
  No network is needed to open the app or to use it — only to activate, and
  occasionally to re-check.
- **Never locked out.** An expired or lapsed licence falls back to a read-only
  Reader mode: everything you already scraped stays readable and exportable.
- **Seats you control.** Each plan covers several computers, and any of them can
  release its seat from the Licence screen.

## 🏷️ Versioning

The project is at the version in **[`VERSION`](VERSION)**, and every change is
recorded in **[`CHANGELOG.md`](CHANGELOG.md)**. Both are written automatically by
[`.github/workflows/version.yml`](.github/workflows/version.yml) when a push lands
on `main` — you never bump a version by hand.

**The scheme.** A feature advances the number by a tenth; a fix or small
adjustment advances the letter. A feature drops the letters, because the fixes
they recorded are now shipped:

```
1.0  ──feat──▶ 1.1  ──feat──▶ 1.2  ──fix──▶ 1.2a  ──fix──▶ 1.2b  ──fix──▶ 1.2c
                                                                    │
                                                                  ──feat──▶ 1.3
```

So two features with three bugs fixed on top reads `1.2c` — the version tells you
what shipped *and* how much repair it needed.

**What counts as a feature** is the commit subject. `feat:` (with an optional
scope — `feat(tui):` — and an optional `!`) is a feature, as is an explicit
`[feature]` or `[minor]` tag. Everything else — `fix:`, `docs:`, `chore:`,
`refactor:`, or no prefix at all — is a fix-level change:

```bash
git commit -m "feat(tui): add Yellow Pages phone lookup"   # 1.1 → 1.2
git commit -m "fix: contacts CSV clobbered itself"         # 1.2 → 1.2a
```

One push is one bump: a push containing five commits, one of them a feature, is a
single feature bump, not five. Merge and release commits are ignored. The letters
roll over past `z` (`1.2z` → `1.2aa`), and the tenths keep counting past nine
(`1.9` → `1.10`) — a major version is a decision, not an accident, so it's never
bumped automatically.

Each release is also tagged (`v1.2c`). To see what a commit *would* do:

```bash
python scripts/bump_version.py --dry-run --commit "feat: add phone lookup"
# 1.0 → 1.1  (feature; 1 commit(s))
```

---

## ⚙️ Configuration

### Email Settings
Edit `email_config.py`:
```python
# Your contact information
FROM_EMAIL = "your@email.com"
FROM_NAME = "Your Name"
PHONE = "(555) 123-4567"
WEBSITE = "https://yourwebsite.com"

# Email settings
SUBJECT_LINE = "Transform Your Business Online"
```

### Scraper Settings
Edit the Python files directly or use command-line arguments:
```python
# In google_maps_scraper.py
max_scrolls = 10        # Number of times to scroll
headless = True         # Run browser in background
timeout = 10            # Seconds to wait for elements

# In contact_scraper.py
page_load_timeout = 30  # Seconds to wait for page load
```

## 📚 Documentation

- **[CHANGELOG.md](CHANGELOG.md)** - Every release, written automatically on each push
- **[QUICK_START.md](docs/QUICK_START.md)** - Get started in 5 minutes
- **[SALES_CALL_README.md](docs/SALES_CALL_README.md)** - Sales Call Cockpit guide
- **[EMAIL_GENERATOR_README.md](docs/EMAIL_GENERATOR_README.md)** - Detailed email generator guide
- **[EMAIL_SENDER_README.md](docs/EMAIL_SENDER_README.md)** - Automated email sending guide
- **[PRICING.md](docs/PRICING.md)** - What the app costs: two pricing models, three tiers
- **[LICENSING.md](docs/LICENSING.md)** - How licensing and payments work, and how to run the licence service
- **[COMPETITIVE_ANALYSIS.md](docs/COMPETITIVE_ANALYSIS.md)** - How this measures up against the market
- **[PRICING_BREAKDOWN.md](docs/PRICING_BREAKDOWN.md)** - Service pricing structure (what *you* charge clients)
- **[EXCLUSIVE_OFFERS_GUIDE.md](docs/EXCLUSIVE_OFFERS_GUIDE.md)** - Special offers documentation
- **[LINK_STRUCTURE.md](docs/LINK_STRUCTURE.md)** - URL and link architecture

## ⚖️ Legal & Ethics

**IMPORTANT**: This tool is provided for educational purposes only.

### Legal Considerations
- ⚠️ Web scraping may violate Google's Terms of Service
- 🔒 Always respect robots.txt and website terms
- 📧 Comply with CAN-SPAM Act and GDPR for email campaigns
- 🚦 Be mindful of rate limiting and server load
- 📜 Consider using official APIs when available

### Best Practices
- ✅ Use data responsibly and ethically
- ✅ Only contact businesses that are relevant to your services
- ✅ Provide clear opt-out mechanisms in emails
- ✅ Respect privacy and data protection laws
- ✅ Don't spam or overload servers with requests
- ✅ Test with small batches before scaling

### Disclaimer
**You are responsible for ensuring your use of this tool complies with all applicable laws and terms of service.** The author assumes no liability for misuse.

## 🐛 Troubleshooting

### ChromeDriver Errors
```bash
# Make sure Chrome browser is installed
# Selenium 4.15+ manages ChromeDriver automatically
pip install --upgrade selenium
```

### No Results Found
```bash
# Run with visible browser to debug
python google_maps_scraper.py "search term" --visible

# Try increasing delays in code
# Check if Google is blocking automated access
```

### Missing Contact Information
- Some businesses may not have all fields available
- Empty strings are returned for missing data
- Use `--visible` flag to see what the scraper sees

### Email Generation Issues
```bash
# Ensure template exists
ls email_template.html

# Check CSV file has email column
head -n 1 contact_details_*.csv

# Run from project root directory
cd /path/to/Google-Scraper
python generate_emails.py
```

### Common Issues

**"No module named 'selenium'"**
```bash
pip install -r requirements.txt
```

**"Template file not found"**
```bash
# Make sure you're in the project directory
cd /Users/jordanlang/Repos/Google-Scraper
```

**"No CSV files found"**
```bash
# Check you have results files in the directory
ls *.csv
```

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Commit your changes**
   ```bash
   git commit -m "Add amazing feature"
   ```
4. **Push to the branch**
   ```bash
   git push origin feature/amazing-feature
   ```
5. **Open a Pull Request**

### Areas for Contribution
- 🐛 Bug fixes and error handling improvements
- 🎨 Email template designs
- 📖 Documentation enhancements
- 🔧 Additional scraping features
- 🌐 International format support
- ⚡ Performance optimizations

## 📝 License

This project is licensed under the MIT License - see below for details:

```
MIT License

Copyright (c) 2024 Jordan Lang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 👤 Author

**Jordan Lang**
- GitHub: [@jordolang](https://github.com/jordolang)
- Website: [jlang.dev](https://jlang.dev)

## 🌟 Show Your Support

If this project helped you, please give it a ⭐️!

## 📞 Contact

For questions, suggestions, or support:
- Open an issue on GitHub
- Visit [jlang.dev](https://jlang.dev)

---

**Made with ❤️ for automating business outreach**

*Last Updated: July 2026*
