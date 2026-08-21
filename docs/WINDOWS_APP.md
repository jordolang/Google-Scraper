# Local Lead Scraper Pro — Windows desktop app

A Windows GUI over the same scraping and outreach pipeline the terminal app
drives. Same code underneath: a search run from the window writes the same CSVs,
into the same folders, as `python app.py`.

![screens](../packaging/app_icon.png)

---

## Getting the .exe

### Option A — download it from CI (nothing to install)

Every push that touches the app builds it on a real Windows runner:

1. Open the repository's **Actions** tab → **Windows App** → the newest run.
2. Download the **LocalLeadScraperPro-windows** artifact.
3. Unzip it. `LocalLeadScraperPro.exe` is a single self-contained file —
   put it anywhere and double-click. There is no installer and nothing is
   written to `Program Files`.

Every release also carries the .exe. When a merge to `main` bumps the version,
`version.yml` tags the release and then calls this workflow for that tag, which
builds the executable and publishes the GitHub release with
`LocalLeadScraperPro.exe` attached — so **Releases** is the place to send
anyone who just wants to run the app:

    https://github.com/jordolang/Google-Scraper/releases/latest

There are three routes to a release, and none of them is a tag push:

| Route | When |
| --- | --- |
| `version.yml` calls this workflow | A merge to `main` bumps the version — the normal path |
| `release: [published]` | You create a release by hand in the GitHub UI |
| **Actions → Windows App → Run workflow**, with a tag | Rebuilding or back-filling a release after the fact |

A tag push drives none of it, for two separate reasons. GitHub starts no new
workflow run for anything pushed with `GITHUB_TOKEN`, which is how
`version.yml` pushes its tag. And a push trigger's `paths` filter applies to
tag pushes too — a tag changes no files, so it can never match the filter, and
a `tags: ["v*"]` entry beside those paths would look right while never firing
once. That combination is why release `v1.5` was published with no `.exe` on
it.

### Option B — build it yourself on a Windows machine

```bat
git clone https://github.com/jordolang/Google-Scraper
cd Google-Scraper
packaging\build_windows.bat
```

The script makes a throwaway virtual environment under `.venv-build\`,
installs the dependencies, renders the icon, and runs PyInstaller. The result
is `dist\LocalLeadScraperPro.exe` (roughly 70–90 MB — it carries its own Python
and Qt).

> PyInstaller cannot cross-compile: a Windows executable has to be produced on
> Windows. That is exactly what the CI job in option A is for.

### Option C — run from source (any OS)

```bash
pip install -r requirements.txt -r requirements-gui.txt
python -m gui            # the app
python -m gui --demo     # sample data: no Chrome, no network, no credentials
```

---

## What you need to run it

| For | You need |
| --- | --- |
| Demo mode | Nothing. It ships with sample data. |
| Scraping Google Maps and websites | Google Chrome installed. Selenium drives your own browser. |
| Sending email | The sending mailbox's **app-specific password**, entered on the Settings page or put in a `.env` file as `EMAIL_PASSWORD=…`. |

---

## The screens

**Dashboard** — location, one or more industries (comma-separated:
`Roofing Contractors, Plumbers, Electricians`), radius, and a per-industry
result cap. Start Scraping fills one tab per industry with the listings; tick
the ones worth chasing.

**Website Scraper** — visits each selected website with a live activity log, a
progress overview (completed / in flight / remaining / data points / elapsed),
and per-category counts: services, images, social profiles, reviews,
certifications, opening hours. Pause and Stop both work mid-run, and whatever
was scanned before a stop is still exported.

**Business Listings** — two grids over everything collected: the raw listings
and the extracted contact data. Search, filter (has email, missing contact
info, scanned, emailed, …), paginate, and export to CSV or Excel.

**Contacts & Outreach** — three tabs:

* *Outreach Dashboard*: where the pipeline stands and what to do next.
* *Email Campaigns*: campaign name, from/reply-to, subject, which industry
  template to render, send delay and daily cap, a recipients grid, a preview
  that opens the composed email in your browser, and a live counter of what was
  sent. **Dry run** composes everything and sends nothing.
* *Call Scripts*: the call queue, the pitch script step by step, and the
  objection handler — both personalised with the business's own name, trade,
  city and review count. Notes and outcomes are recorded per call.

**Settings** — sending account and SMTP (with a Test Connection button that
logs in and hangs up without sending), headless/visible Chrome, demo mode,
export folder, licence text.

**Tools** — look up missing phone numbers on Google and Yellow Pages, edit the
package prices the emails and scripts quote, and load a previous export back
into the app.

**Logs** — every step of every run, filterable by source, savable to a file.

---

## Where things are stored

Run from a packaged .exe, the app keeps its files under
`%LOCALAPPDATA%\LocalLeadScraperPro\`:

| What | Where |
| --- | --- |
| Scrape exports | `data\<search term>\<location>\listings*.csv`, `contacts*.csv` |
| Editable email templates | `email_templates\` (copied out of the bundle on first run) |
| Editable call script | `pitch_script.md` |
| Package prices | `pricing.json` |
| SMTP password | Nowhere. It lives in memory for the session, or in a `.env` you control. |

App preferences (window settings, last search, licence text) live in
`%APPDATA%\LocalLeadScraperPro\settings.json`. Change the export folder on the
Settings page if you would rather keep the CSVs somewhere else.

Run from source, all of these are just the files in the repo.

---

## Honest limits

* **Email opens, clicks and replies are not tracked.** Direct SMTP has no way
  to report them, so those counters stay blank. They would need an email
  service provider with tracking (SendGrid, Mailgun, …).
* **Google Maps has no radius filter.** The Radius control records your intent
  and sizes how far the results feed is scrolled; proximity ranking is done by
  Maps from the location you type.
* **Chrome version drift** is the usual cause of a scrape that fails
  immediately. Update Google Chrome and try again; Selenium Manager fetches the
  matching driver by itself.

---

## Development

```bash
QT_QPA_PLATFORM=offscreen pytest tests/test_gui.py tests/test_gui_flow.py -q
```

The GUI tests run headless — they build the real window, run a demo search,
scan, export and compose, and never need a display. `LocalLeadScraperPro.exe
--selftest` does the same check inside a packaged build and is what the Windows
CI job runs before publishing the artifact.

Layout:

```
gui/
  app.py            window shell, navigation, --selftest
  theme.py          colour tokens + the Qt stylesheet
  state.py          the lead list and settings every page shares
  workers.py        background jobs, pause/stop
  services.py       pipeline factory, CSV/XLSX writers
  runtime.py        where files live, packaged vs. from source
  scripts.py        call-script steps and objection cards
  pages/            one module per screen
  widgets/          cards, tables, stats, the navigation rail
packaging/
  LocalLeadScraperPro.spec   PyInstaller build
  build_windows.bat          one-command Windows build
  make_icon.py               renders the multi-size .ico
```
