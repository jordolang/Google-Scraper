"""The Textual application tying the whole outreach pipeline together.

Flow (each step is its own screen; ``→`` advances, ``Esc`` goes back):

    Search  →  Results (pick businesses)  →  Contacts (pick who to email)
            →  Compose (edit each email)  →  Send

Run with ``python scraper_tui.py`` – add ``--demo`` to explore without a
browser, network, or SMTP credentials.
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from textual.app import App
from textual.binding import Binding

from .models import Business, EmailMessage
from .pipeline import Pipeline, make_pipeline
from .pipeline_screens import (  # noqa: F401  (re-exported for compatibility)
    ComposeScreen, ContactsScreen, ResultsScreen, SearchScreen, SendScreen,
)


# --------------------------------------------------------------------------- #
#  The application
# --------------------------------------------------------------------------- #
class ScraperTUI(App):
    """Top-level app; holds pipeline + the state shared between screens."""

    CSS = """
    Screen { align: center top; }
    .title { padding: 1 0 0 0; text-style: bold; }
    .hint { color: $text-muted; padding: 0 0 1 0; }
    .readonly { color: $text-muted; padding: 0 0 1 0; }
    #search-body, #results-body, #contacts-body, #compose-body, #send-body {
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
    """

    BINDINGS = [Binding("ctrl+c", "quit", "Quit", priority=True)]

    def __init__(self, pipeline: Pipeline, demo: bool = False) -> None:
        super().__init__()
        self.pipeline = pipeline
        self.demo = demo
        self.businesses: List[Business] = []
        self.chosen: List[Business] = []
        self.contacts: List[Business] = []
        self.messages: List[EmailMessage] = []

    def on_mount(self) -> None:
        self.title = "Google Scraper — Outreach Studio"
        self.sub_title = "demo mode" if self.demo else "live mode"
        self.push_screen(SearchScreen())


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Interactive TUI: search businesses, scrape contacts, and send outreach emails."
    )
    parser.add_argument("--demo", action="store_true",
                        help="Use built-in sample data (no browser, network, or credentials).")
    parser.add_argument("--from-email", default="jordan@jlang.dev",
                        help="Sender email address (default: jordan@jlang.dev).")
    parser.add_argument("--template", default="email_template.html",
                        help="Path to the HTML email template.")
    parser.add_argument("--visible", action="store_true",
                        help="Run the scraper browser in visible (non-headless) mode.")
    args = parser.parse_args(argv)

    pipeline = make_pipeline(
        demo=args.demo,
        from_email=args.from_email,
        template_path=args.template,
        headless=not args.visible,
    )
    ScraperTUI(pipeline=pipeline, demo=args.demo).run()


if __name__ == "__main__":
    main()
