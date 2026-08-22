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


## What is inside the .exe, and what is not

Everything the app needs is in the one file. Nothing is installed and nothing
is downloaded — including the browser:

| | |
| --- | --- |
| Python itself, PySide6, Selenium, BeautifulSoup, lxml | bundled |
| The app, its email templates, the pitch script | bundled |
| **chromedriver** | bundled — see below |
| **Chromium** (the browser itself) | bundled |

Nothing needs to be installed, not even a browser. The executable carries a
Chromium build and the chromedriver from the same snapshot revision, so the two
always match — the version-mismatch problem that normally comes with driving
Chrome cannot arise.

Chromium rather than Google Chrome: Chromium is the open-source project and can
be redistributed inside another product; Google's Chrome binaries cannot. If a
Chrome is already installed and you would rather drive that, delete the
unpacked browser folder (below) and the app falls back to it.

### How the browser rides along

PyInstaller's one-file mode unpacks everything it bundles to a temp folder on
*every* launch, so putting ~250 MB of browser in the bundle would add a long
pause to every start. It is appended to the executable instead, after
PyInstaller's own archive — zip finds its central directory from the end of a
file, so the app can read its own payload, and the bootloader does not care
what follows its archive.

The first scrape unpacks it once to

    %LOCALAPPDATA%\LocalLeadScraperPro\browser\<revision>\

and says so in the progress log; every launch after that is immediate. Delete
that folder to reclaim the space, or to force a fall back to an installed
Chrome — it is rebuilt from the executable on the next run.

### The bundled chromedriver

Selenium normally downloads a driver the first time it runs ("Selenium
Manager") — a download nobody asked for, that needs internet and fails behind a
locked-down network. `packaging/fetch_chromedriver.py` puts one in the bundle
at build time instead, and the app adds it to `PATH` at startup so Selenium
finds it and downloads nothing.

A driver only drives its own major version of Chrome, and Chrome updates
itself. When the two do not match the app steps out of the way and lets
Selenium fetch a matching driver — that needs the network, but it works, which
beats refusing to run. Each release bundles the driver for the then-current
stable Chrome, so the normal case stays offline.

## The Mac builds

The same app, built as a `.app` bundle on real Mac runners — `macos-13` for
Intel and `macos-14` for Apple Silicon, because neither PyInstaller nor Qt
cross-compiles. PySide6 ships a `universal2` wheel, so the Python side is
identical between them; what differs is the machine and the Chromium build
that goes with it (`Mac` and `Mac_Arm` snapshots respectively).

Releases carry them zipped, since a `.app` is a directory and a release asset
is a single file:

| File | For |
| --- | --- |
| `LocalLeadScraperPro-macos-apple-silicon.zip` | M1 and later |
| `LocalLeadScraperPro-macos-intel.zip` | Intel Macs |

Unzip, drag **Local Lead Scraper Pro** to Applications, and the first launch
needs one extra step: the app is not signed with an Apple Developer
certificate, so Gatekeeper refuses a plain double-click with "cannot be opened
because the developer cannot be verified". **Right-click the app → Open →
Open** once, and macOS remembers the choice. From the terminal the equivalent
is:

    xattr -dr com.apple.quarantine "/Applications/Local Lead Scraper Pro.app"

Signing and notarising would remove that step; it needs a paid Apple Developer
account and the certificate stored as repository secrets, which is a decision
for whoever owns the account rather than something the build can do on its
own.

## Why the bundle collects selenium whole

Selenium 4 resolves its driver classes through a lazy string map:

```python
"ChromeOptions": ("selenium.webdriver.chrome.options", "Options"),
```

Those module paths are strings in a dict, looked up by `__getattr__` when the
attribute is first touched. PyInstaller's static analysis cannot see them, so a
hand-written list of `hiddenimports` only ever contains the submodules someone
remembered — and the resulting .exe starts perfectly, shows every screen, and
then dies the moment Start Scraping is pressed:

    ModuleNotFoundError: No module named 'selenium.webdriver.chrome.options'

`collect_submodules("selenium")` in the spec is what prevents that, and
`tests/test_gui.py::test_the_spec_collects_selenium_whole` fails if anyone
replaces it with a hand-written list again.

The same shape of bug is why `--selftest` imports `RUNTIME_IMPORTS` and runs a
whole demo pipeline rather than only building the windows: anything imported
lazily, inside a function, is invisible to the packager and therefore able to
go missing without the build noticing.

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
