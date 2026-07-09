#!/usr/bin/env python3
"""Launcher for the interactive outreach TUI.

    python scraper_tui.py            # live mode (drives Chrome + SMTP)
    python scraper_tui.py --demo     # explore the whole flow with sample data

See ``python scraper_tui.py --help`` for all options.
"""

from tui.app import main

if __name__ == "__main__":
    main()
