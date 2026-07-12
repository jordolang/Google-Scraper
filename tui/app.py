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
    CompleteScreen, ComposeScreen, ContactsScreen, ResultsScreen, SearchScreen, SendScreen,
)

_CSS = """
Screen { align: center top; }
.title { padding: 1 0 0 0; text-style: bold; }
.hint { color: $text-muted; padding: 0 0 1 0; }
.readonly { color: $text-muted; padding: 0 0 1 0; }
#home-body, #search-body, #results-body, #contacts-body, #compose-body,
#send-body, #complete-body, #cockpit-menu-body, #sheet-body, #prep-body, #call-body {
    width: 100%; max-width: 120; padding: 1 2;
}
Input { margin: 0 0 1 0; }
Input.tiny { width: 8; }
#search-actions, #results-actions, #contacts-actions, #compose-actions, #send-actions,
#complete-actions {
    height: auto; padding: 1 0; align-horizontal: right;
}
#search-actions Button, #results-actions Button, #contacts-actions Button,
#compose-actions Button, #send-actions Button { margin: 0 0 0 2; }
#complete-actions Button { margin: 0 0 0 2; }
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
ModalScreen { align: center middle; }
#disp-body, #cb-body, #obj-body {
    width: 80; max-width: 90%; height: auto; padding: 1 2;
    background: $surface; border: thick $primary;
}
#disp-list, #obj-list { height: auto; max-height: 12; border: round $primary; }
#obj-detail { height: auto; }
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

    def reset_pipeline_state(self) -> None:
        """Clear campaign data before starting another end-to-end run."""
        self.businesses = []
        self.chosen = []
        self.contacts = []
        self.messages = []

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
