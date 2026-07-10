#!/usr/bin/env python3
"""Shim: launch the unified outreach app straight into the scrape→email pipeline.

    python scraper_tui.py            # live mode (drives Chrome + SMTP)
    python scraper_tui.py --demo     # explore with sample data

Equivalent to ``python app.py --start pipeline``.
"""

import sys

from tui.app import main

if __name__ == "__main__":
    main(sys.argv[1:] + ["--start", "pipeline"])
