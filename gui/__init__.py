"""Windows desktop front end for the Local Lead Scraper Pro toolkit.

The GUI is a thin Qt layer over the same pipeline the terminal UI drives, so
scraping, contact extraction and outreach all behave identically whichever
front end is used.

    python -m gui            # run it
    python -m gui --demo     # tour it with sample data, no browser needed
"""

__all__ = ["main"]


def main(argv=None) -> int:
    from .app import main as _main

    return _main(argv)
