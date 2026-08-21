"""End-to-end tests that drive a real browser.

Skipped unless ``LLSP_LIVE_TESTS=1`` and both Chrome and a matching driver are
on PATH, because they need a browser and a few seconds each. They exist
because the packaged app's whole job is to drive Chrome: the offscreen suite
proves the windows and the wiring, and these prove the thing that actually
failed on a user's desk — the live scraping path.

Run them with:

    LLSP_LIVE_TESTS=1 QT_QPA_PLATFORM=offscreen pytest tests/test_live_scrape.py
"""

from __future__ import annotations

import os
import shutil
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LLSP_LIVE_TESTS") != "1"
    or not (shutil.which("google-chrome") or shutil.which("chrome")
            or shutil.which("chromium")),
    reason="live browser tests are opt-in (set LLSP_LIVE_TESTS=1 with Chrome installed)",
)

SITE = """<html><head><title>Acme Roofing</title></head><body>
<nav><ul><li>Home</li><li>About</li></ul></nav>
<h2>Our Services</h2><ul><li>Roof Repair</li><li>New Roofs</li><li>Gutter Guards</li></ul>
<p>Email <a href="mailto:hello@acmeroofing.example">hello@acmeroofing.example</a></p>
<p>Call (614) 555-0142 &mdash; Owner: Dana Rivera</p>
<a href="https://www.facebook.com/acmeroofing">Facebook</a>
<a href="https://notfacebook.com/nope">Not Facebook</a>
<img src="a.jpg"><img src="b.jpg"><img src="c.jpg">
</body></html>"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """A tiny local website, so the tests never touch anyone's server."""
    root = tmp_path_factory.mktemp("site")
    (root / "index.html").write_text(SITE, encoding="utf-8")
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


def test_the_real_scraper_reads_a_live_page(site):
    """The contact scraper, driving a real Chrome, against a real page."""
    from contact_scraper import ContactScraper

    scraper = ContactScraper(headless=True)
    try:
        info = scraper.scrape_website(site)
    finally:
        scraper.close()

    assert info["emails"] == ["hello@acmeroofing.example"]
    assert info["contact_names"] == ["Dana Rivera"]
    # One entry per number: the two regexes overlap and used to yield both
    # "(614) 555-0142" and the malformed "614) 555-0142".
    assert info["phones"] == ["(614) 555-0142"]
    # A host that merely ends with a social domain is not a social profile.
    assert info["social_links"] == ["https://www.facebook.com/acmeroofing"]
    # Services counted from the services section, not the nav.
    assert info["insights"]["services"] == 3
    assert info["insights"]["images"] == 3


def test_the_window_scans_a_live_site_end_to_end(site, monkeypatch, tmp_path):
    """Drive the real window: a lead in, a live scan, contacts on screen.

    This is the path that broke in the packaged build — the GUI worker thread
    calling into Selenium — so it is worth exercising for real.
    """
    from PySide6.QtWidgets import QApplication

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LLSP_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GOOGLE_SCRAPER_DATA_DIR", str(tmp_path / "data"))

    from gui.app import build_app
    from tui.models import Business

    app, window = build_app([])
    try:
        window.state.settings["demo_mode"] = False   # the live pipeline
        window.state.settings["headless"] = True
        window.state.add_businesses(
            [Business(name="Acme Roofing", website=site, search_term="Roofing")],
            "Roofing")
        for lead in window.state.leads:
            lead.selected = True

        window.go_to("scraper")
        scraper = window.pages["scraper"]
        scraper.start()

        waited = 0
        while scraper.runner.running and waited < 120_000:
            QApplication.processEvents()
            app.thread().msleep(50)
            waited += 50
        QApplication.processEvents()

        lead = window.state.leads[0]
        assert lead.business.emails == ["hello@acmeroofing.example"], (
            f"live scan found {lead.business.emails!r}")
        assert lead.business.phones == ["(614) 555-0142"]
        assert lead.business.scanned

        # And the run wrote its CSVs where the app says it does.
        contacts = list((tmp_path / "data").rglob("contacts*.csv"))
        assert contacts, "the live scan exported no contacts CSV"
        assert "hello@acmeroofing.example" in contacts[0].read_text(encoding="utf-8")
    finally:
        window.close()
