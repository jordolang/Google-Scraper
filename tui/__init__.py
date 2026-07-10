"""Interactive terminal UI for the Google Maps scraping + outreach pipeline.

The :mod:`tui` package wires together the existing command-line tools
(:class:`google_maps_scraper.GoogleMapsScraper`,
:class:`contact_scraper.ContactScraper`, :class:`generate_emails.EmailGenerator`
and :class:`send_emails.EmailSender`) behind a single, navigable
`Textual <https://textual.textualize.io/>`_ application.

Launch it with ``python scraper_tui.py`` (add ``--demo`` to explore the flow
without a browser or network connection).
"""

__all__ = ["models", "pipeline", "app"]
