"""Help — what each screen does and how to get unstuck."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QTextBrowser

from .. import settings_store, theme
from ..widgets.common import Card, button, hint, title
from . import Page

HELP = """
## Getting started

1. **Dashboard** — type a city and one or more industries (comma-separated:
   `Roofing Contractors, Plumbers, Electricians`), then press **Start Scraping**.
   Each industry gets its own tab of results.
2. Tick the businesses worth chasing and press **Go to Website Scraper**.
3. **Website Scraper** — visits each website and pulls out emails, phone
   numbers, contact names and what the site actually shows: services, images,
   social profiles, certifications, opening hours.
4. **Business Listings** — filter, search and export everything collected,
   as CSV or as an Excel workbook.
5. **Contacts & Outreach** — compose from the industry email templates and
   send over SMTP, or work the **Call Scripts** tab with the pitch script and
   the objection handler in front of you.

## Demo mode

Settings → Scraping → **Demo mode** replaces the browser with built-in sample
data. Every screen behaves normally: nothing is fetched, nothing is sent, and
no credentials are needed. It is the fastest way to learn the app.

## Requirements for live runs

* **Google Chrome** installed — Selenium drives your real Chrome.
* An **app-specific password** for the sending mailbox, entered on the
  Settings page or placed in a `.env` file as `EMAIL_PASSWORD=…`.

## Where things are saved

* Scrape exports: `<export folder>/<search term>/<location>/listings*.csv`
  and `contacts*.csv`. Change the export folder on the Settings page.
* App preferences: `{config}`.
* Prices quoted in emails and call scripts: `pricing.json` — edit them under
  **Tools → Package Pricing**.
* The call script itself: `pitch_script.md`. Edit that file and the Call
  Scripts tab follows.

## When something goes wrong

* **The scrape fails immediately** — Chrome is missing or a different version
  than the driver expects. Install/update Google Chrome, then try again.
* **Emails will not send** — use **Test Connection** on the Settings page.
  iCloud custom domains need the Apple ID that owns the domain as the SMTP
  username, not the alias in the From: header.
* **Nothing shows in a table** — check the filter dropdown; it persists
  between visits.
* The **Logs** page shows this session's activity — the most recent few
  thousand lines, held in memory and gone when the app closes. Save it to a
  file from that page before quitting if you need to keep or send it.

## What this app cannot do

* Email opens, clicks and replies are not tracked — direct SMTP has no way to
  report them. Those counters stay blank unless you move sending to a provider
  that offers tracking.
* Google Maps has no radius filter; the Radius control records your intent and
  sizes how far the results feed is scrolled.
"""


class HelpPage(Page):
    heading = "Help"

    def __init__(self, state, parent=None) -> None:
        super().__init__(state, parent)
        self.root().addWidget(title("HELP"))
        card = Card()
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setStyleSheet(
            f"QTextBrowser {{ border: none; background: {theme.CARD}; padding: 4px; }}")
        view.setMarkdown(HELP.format(config=settings_store.config_path()))
        card.add(view, 1)
        self.root().addWidget(card, 1)

        actions = QHBoxLayout()
        actions.addWidget(hint("Local Lead Scraper Pro — desktop front end for the "
                               "Jlang.dev outreach toolkit."))
        actions.addStretch(1)
        readme = button("Open README")
        logs = button("Open Logs")
        readme.clicked.connect(self._open_readme)
        logs.clicked.connect(lambda: self._navigate("logs"))
        actions.addWidget(readme)
        actions.addWidget(logs)
        self.root().addLayout(actions)

    def _open_readme(self) -> None:
        from pathlib import Path

        path = Path("README.md").resolve()
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _navigate(self, key: str) -> None:
        window = self.window()
        if hasattr(window, "go_to"):
            window.go_to(key)
