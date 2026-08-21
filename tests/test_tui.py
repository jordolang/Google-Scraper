"""Tests for the interactive outreach TUI (``tui`` package).

These exercise the model/pipeline layer directly and drive the full Textual
app end-to-end in demo mode via an in-process pilot.  Everything runs headless
and offline — no browser, network, or SMTP credentials required.
"""

import asyncio
from pathlib import Path
from unittest import mock

import pytest

from tui.models import Business, EmailMessage, ScanEvent
from tui.pipeline import DemoPipeline, LivePipeline, make_pipeline
from tui.pitch_script import load_pitch_script


# --------------------------------------------------------------------------- #
#  models
# --------------------------------------------------------------------------- #
def test_business_from_dict_splits_multi_values():
    b = Business.from_dict(
        {
            "name": "Acme",
            "category": "Plumber",
            "email": "a@x.com, b@x.com",
            "scraped_phone": "111, 222",
            "contact_name": "Jane Doe",
            "rating": "4.5",
        }
    )
    assert b.name == "Acme"
    assert b.emails == ["a@x.com", "b@x.com"]
    assert b.phones == ["111", "222"]
    assert b.contact_names == ["Jane Doe"]
    assert b.primary_email == "a@x.com"
    assert b.has_email is True


def test_business_no_email():
    b = Business(name="Nope", website="http://x")
    assert b.has_email is False
    assert b.primary_email == ""
    assert "no contact info" in b.contact_line


def test_to_generator_row_roundtrips_email_fields():
    b = Business(
        name="Acme",
        emails=["a@x.com", "b@x.com"],
        phones=["111"],
        contact_names=["Jane"],
        category="Plumber",
    )
    row = b.to_generator_row()
    assert row["email"] == "a@x.com, b@x.com"
    assert row["scraped_phone"] == "111"
    assert row["contact_name"] == "Jane"
    assert row["category"] == "Plumber"


def test_email_message_label():
    b = Business(name="Acme")
    m = EmailMessage(business=b, to_email="a@x.com", subject="Hi", html="<p>x</p>")
    assert m.label == "Acme  →  a@x.com"


# --------------------------------------------------------------------------- #
#  pipeline
# --------------------------------------------------------------------------- #
def test_make_pipeline_selects_implementation():
    assert isinstance(make_pipeline(demo=True), DemoPipeline)
    assert isinstance(make_pipeline(demo=False), LivePipeline)


def test_demo_pipeline_full_flow_offline():
    pipeline = DemoPipeline()
    logs = []
    businesses = pipeline.search("electricians", "Columbus, OH", progress=logs.append)
    assert len(businesses) == 5
    assert logs  # progress was streamed

    pipeline.scrape_contacts(businesses)
    with_email = [b for b in businesses if b.has_email]
    assert len(with_email) == 3
    assert all(b.scanned for b in businesses)

    msg = pipeline.build_message(with_email[0])
    assert msg.to_email == with_email[0].primary_email
    assert with_email[0].name in msg.html

    stats = pipeline.send([msg], password="", dry_run=True)
    assert stats["total"] == 1
    assert stats["sent"] == 0  # dry run sends nothing

    stats = pipeline.send([msg], password="", dry_run=False)
    assert stats["sent"] == 1


def test_scrape_contacts_emits_scan_events():
    pipeline = DemoPipeline()
    businesses = pipeline.search("electricians", "Columbus, OH")
    events = []
    pipeline.scrape_contacts(businesses, on_event=events.append)

    # One "scanning" + one terminal event per business with a website; the
    # website-less sample only produces the terminal "skipped" event.
    with_site = [b for b in businesses if b.website]
    terminal = [e for e in events if e.finished]
    assert len(terminal) == len(businesses)
    assert len([e for e in events if not e.finished]) == len(with_site)
    assert [e.index for e in terminal] == list(range(1, len(businesses) + 1))
    assert all(e.total == len(businesses) for e in events)

    skipped = [e for e in terminal if e.status == "skipped"]
    assert len(skipped) == 1
    # The one sample business with no website; its name follows the search term.
    assert skipped[0].name == next(b.name for b in businesses if not b.website)

    done = [e for e in terminal if e.status == "done"]
    assert sum(1 for e in done if e.emails) == 3
    assert sum(len(e.phones) for e in done) == 4


def test_scan_tally_folds_events():
    from tui.pipeline_screens import ScanTally

    tally = ScanTally(total=3)
    tally.record(ScanEvent(1, 3, "A", status="done", emails=["a@x.com"], phones=["1", "2"]))
    tally.record(ScanEvent(2, 3, "B", status="skipped"))
    tally.record(ScanEvent(3, 3, "C", status="error", error="boom"))

    assert (tally.scanned, tally.with_email) == (3, 1)
    assert (tally.emails, tally.phones) == (1, 2)
    assert (tally.skipped, tally.errors) == (1, 1)


def test_live_pipeline_scan_survives_one_bad_website():
    """A site that blows up must be recorded as an error, not abort the batch."""

    class Boom:
        def scrape_website(self, url):
            if "bad" in url:
                raise RuntimeError("connection reset")
            return {"emails": ["ok@x.com"], "phones": ["555"], "contact_names": []}

        def close(self):
            pass

    pipeline = LivePipeline()
    businesses = [
        Business(name="Bad", website="http://bad.example"),
        Business(name="Good", website="http://good.example"),
    ]
    events = []
    with mock.patch("contact_scraper.ContactScraper", return_value=Boom()), \
            mock.patch("tui.pipeline.time.sleep"):
        pipeline.scrape_contacts(businesses, on_event=events.append)

    terminal = {e.name: e for e in events if e.finished}
    assert terminal["Bad"].status == "error"
    assert "connection reset" in terminal["Bad"].error
    assert terminal["Good"].status == "done"
    assert businesses[1].emails == ["ok@x.com"]
    assert all(b.scanned for b in businesses)


def test_demo_send_skips_missing_address():
    pipeline = DemoPipeline()
    b = Business(name="NoAddr")
    msg = EmailMessage(business=b, to_email="", subject="s", html="h")
    stats = pipeline.send([msg], password="", dry_run=False)
    assert stats["skipped"] == 1
    assert stats["sent"] == 0


# --------------------------------------------------------------------------- #
#  full app navigation (headless pilot)
# --------------------------------------------------------------------------- #
def test_app_navigates_entire_flow():
    from tui.app import (
        ComposeScreen,
        CompleteScreen,
        ContactsScreen,
        CustomizeScreen,
        ResultsScreen,
        ScraperTUI,
        SearchScreen,
        SendScreen,
    )

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, SearchScreen)

            app.screen.query_one("#field").value = "electricians"
            app.screen.query_one("#location").value = "Columbus, OH"
            await pilot.click("#go")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ResultsScreen)
            assert len(app.businesses) == 5
            scan = app.screen.query_one("#scan")
            assert "Continue" in str(scan.label)
            assert scan.tooltip

            await pilot.click("#scan")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ContactsScreen)

            await pilot.click("#compose")
            await pilot.pause()
            assert isinstance(app.screen, CustomizeScreen)
            assert len(app.recipients) == 3

            # Customize screen builds the messages and advances to Compose.
            await pilot.click("#compose")
            await pilot.pause()
            assert isinstance(app.screen, ComposeScreen)
            assert len(app.messages) == 3

            # Editing subject and switching recipients must persist per message.
            app.screen.query_one("#subject-field").value = "Edited 0"
            app.screen.query_one("#recipient-list").highlighted = 1
            await pilot.pause()
            app.screen.query_one("#subject-field").value = "Edited 1"
            app.screen.query_one("#recipient-list").highlighted = 0
            await pilot.pause()
            assert app.messages[0].subject == "Edited 0"
            assert app.messages[1].subject == "Edited 1"

            await pilot.click("#send")
            await pilot.pause()
            assert isinstance(app.screen, SendScreen)

            # Dry run is the default, so this is safe and sends nothing.
            await pilot.click("#do-send")
            await app.workers.wait_for_complete()
            await pilot.pause()

            finish = app.screen.query_one("#finish")
            assert finish.disabled is False
            await pilot.click("#finish")
            await pilot.pause()
            assert isinstance(app.screen, CompleteScreen)

            await pilot.click("#restart")
            await pilot.pause()
            assert isinstance(app.screen, SearchScreen)
            assert app.businesses == []
            assert app.contacts == []
            assert app.messages == []

    asyncio.run(scenario())


def test_results_screen_shows_scan_progress_and_totals():
    """The scan panel must fill its bar and counters as websites are scanned."""
    from tui.app import ResultsScreen, ScraperTUI

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#field").value = "electricians"
            await pilot.click("#go")
            await app.workers.wait_for_complete()
            await pilot.pause()

            results = app.screen
            assert isinstance(results, ResultsScreen)
            bar = results.query_one("#scan-progress")
            assert bar.progress == 0

            await pilot.click("#scan")
            await app.workers.wait_for_complete()
            await pilot.pause()

            # The bar is full and the tally matches the demo sample data:
            # 5 businesses, 3 with an email, 1 with no website to visit.
            assert bar.total == 5
            assert bar.progress == 5
            assert bar.percentage == 1.0
            tally = results._tally
            assert (tally.scanned, tally.with_email, tally.skipped) == (5, 3, 1)
            assert tally.emails == 4  # one sample site lists two addresses
            stats = str(results.query_one("#scan-stats").render())
            assert "4 email(s)" in stats and "4 phone(s)" in stats
            assert "no website" in stats
            assert str(results.query_one("#scan-count").render()).strip() == "5/5"
            assert "complete" in str(results.query_one("#scan-current").render()).lower()

    asyncio.run(scenario())


def test_hotkeys_advance_the_whole_workflow():
    """Every step must be reachable from the key spelled out under its list."""
    from tui.app import (
        ComposeScreen,
        CompleteScreen,
        ContactsScreen,
        CustomizeScreen,
        ResultsScreen,
        ScraperTUI,
        SearchScreen,
        SendScreen,
    )

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#field").value = "electricians"
            app.screen.query_one("#location").value = "Zanesville, OH"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ResultsScreen)

            # s: scan the selected websites and move on to the contacts.
            await pilot.press("s")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ContactsScreen)

            # c: customize (industry + pricing). ctrl+s: build + compose.
            await pilot.press("c")
            await pilot.pause()
            assert isinstance(app.screen, CustomizeScreen)

            await pilot.press("ctrl+s")
            await pilot.pause()
            assert isinstance(app.screen, ComposeScreen)

            # ctrl+s again: on to sending.
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert isinstance(app.screen, SendScreen)

            # Dry run is on by default, so ctrl+s here sends nothing real.
            await pilot.press("ctrl+s")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("ctrl+f")
            await pilot.pause()
            assert isinstance(app.screen, CompleteScreen)

    asyncio.run(scenario())


def test_results_screen_can_skip_the_scan_and_go_straight_to_email():
    from tui.app import ContactsScreen, ResultsScreen, ScraperTUI

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#field").value = "electricians"
            await pilot.click("#go")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ResultsScreen)

            await pilot.press("e")
            await pilot.pause()
            assert isinstance(app.screen, ContactsScreen)
            # Nothing was scanned — we jumped ahead with the listing data.
            assert app.contacts == app.businesses
            assert not any(b.scanned for b in app.contacts)

    asyncio.run(scenario())


def test_phone_lookup_from_the_contacts_screen():
    """A business the scan drew a blank on gets a number from a directory search."""
    from tui.app import ContactsScreen, ScraperTUI

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#field").value = "electricians"
            await pilot.click("#go")
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Skip the scan so nobody has contact info yet.
            await pilot.press("e")
            await pilot.pause()
            assert isinstance(app.screen, ContactsScreen)
            assert not any(b.has_contact_info for b in app.contacts)

            await pilot.press("g")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert all(b.phones for b in app.contacts)
            assert all(b.phone_source == "google" for b in app.contacts)
            # The found numbers are on screen, tagged with where they came from.
            options = app.screen.query_one("#contacts-list").options
            assert any("via google" in str(o.prompt) for o in options)
            # ...and exported.
            assert app.pipeline.last_contacts_csv.exists()

    asyncio.run(scenario())


def test_open_html_preview_writes_utf8_and_opens_a_browser_window():
    """The preview helper drops the HTML on disk and hands the browser a file:// URL."""
    from tui.pipeline_screens import open_html_preview

    html = "<html><body><p>Hi ✉ Bright Spark ★</p></body></html>"
    with mock.patch("tui.pipeline_screens.webbrowser.open") as opened:
        path = open_html_preview(html, "Bright Spark Electric")

    assert path.exists()
    assert path.suffix == ".html"
    assert "bright-spark-electric" in path.name
    # Non-ASCII survives the round trip; the templates are full of it.
    assert path.read_text(encoding="utf-8") == html
    url, = opened.call_args.args
    assert url == path.resolve().as_uri()
    # new=1 asks for a window rather than a tab.
    assert opened.call_args.kwargs["new"] == 1
    path.unlink()


def test_compose_screen_previews_the_edited_html_in_a_browser():
    """The preview button flushes pending edits, then opens the current email."""
    from tui.app import ComposeScreen, ContactsScreen, CustomizeScreen, ScraperTUI

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#field").value = "electricians"
            await pilot.click("#go")
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Scan for real (demo data) so the contacts have email addresses.
            await pilot.click("#scan")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ContactsScreen)
            await pilot.click("#compose")
            await pilot.pause()
            assert isinstance(app.screen, CustomizeScreen)
            await pilot.click("#compose")
            await pilot.pause()
            assert isinstance(app.screen, ComposeScreen)

            # An unsaved edit in the body editor must reach the preview.
            edited = "<html><body><p>Edited in the TUI ✉</p></body></html>"
            app.screen.query_one("#body-field").text = edited

            with mock.patch("tui.pipeline_screens.open_html_preview") as opener:
                opener.return_value = Path("preview.html")
                await pilot.click("#preview")
                await app.workers.wait_for_complete()
                await pilot.pause()

            opener.assert_called_once()
            assert opener.call_args.args[0] == edited
            assert app.messages[0].html == edited

            # Leaving the screen while the browser is still starting: the worker
            # comes back to post its toast against a screen that is gone.
            with mock.patch("tui.pipeline_screens.open_html_preview") as opener:
                opener.return_value = Path("preview.html")
                await pilot.click("#preview")
                await pilot.click("#back")
                await app.workers.wait_for_complete()
                await pilot.pause()
            assert not isinstance(app.screen, ComposeScreen)

    asyncio.run(scenario())


def test_load_pitch_script_returns_content():
    text = load_pitch_script()
    assert "Pitch Script" in text
    # Pricing figures from the guide should be present.
    assert "400" in text


def test_load_pitch_script_falls_back_when_missing(tmp_path):
    missing = tmp_path / "does_not_exist.md"
    text = load_pitch_script(missing)
    assert "Pitch Script" in text  # built-in fallback


def test_pitch_script_modal_opens_from_any_screen():
    from tui.app import (
        ContactsScreen,
        PitchScriptScreen,
        ResultsScreen,
        ScraperTUI,
        SearchScreen,
    )

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, SearchScreen)

            # Open from the search screen and toggle closed.
            await pilot.press("ctrl+g")
            await pilot.pause()
            assert isinstance(app.screen, PitchScriptScreen)
            assert app.screen.query_one("#script-viewer") is not None
            await pilot.press("ctrl+g")
            await pilot.pause()
            assert isinstance(app.screen, SearchScreen)

            # Advance a couple of screens, then confirm it still opens mid-flow.
            app.screen.query_one("#field").value = "electricians"
            await pilot.click("#go")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ResultsScreen)
            await pilot.press("ctrl+g")
            await pilot.pause()
            assert isinstance(app.screen, PitchScriptScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, ResultsScreen)

    asyncio.run(scenario())


def test_app_requires_search_term():
    from tui.app import ScraperTUI, SearchScreen

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#go")  # empty field
            await pilot.pause()
            # Stays on the search screen when nothing was entered.
            assert isinstance(app.screen, SearchScreen)
            assert app.businesses == []

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
#  industry template + pricing wiring
# --------------------------------------------------------------------------- #
def test_build_message_honours_industry_kwarg():
    pipeline = DemoPipeline()
    b = Business(name="Bella Salon", category="Hair salon", address="1 St, Dublin, OH",
                 emails=["bella@example.com"])
    msg = pipeline.build_message(b, industry_key="beauty_personal_care")
    assert "salons & studios" in msg.html  # rendered the beauty template


def test_customize_screen_preselects_industry_and_applies_price_override():
    from tui.app import ComposeScreen, CustomizeScreen, ScraperTUI
    from textual.widgets import Select

    async def scenario():
        app = ScraperTUI(pipeline=make_pipeline(demo=True), demo=True)
        async with app.run_test(size=(120, 44)) as pilot:
            # Walk to the contacts screen, then into Customize.
            await pilot.pause()
            app.screen.query_one("#field").value = "electricians"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.click("#scan")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.click("#compose")  # contacts -> customize
            await pilot.pause()
            assert isinstance(app.screen, CustomizeScreen)

            # The demo businesses are electricians -> trades template preselected.
            sel = app.screen.query_one("#industry", Select)
            assert sel.value == "home_trade_services"

            # Override this business's Launchpad email price, then advance.
            app.screen.query_one("#price-launchpad_sale").value = "$275"
            await pilot.click("#compose")  # customize -> compose (builds messages)
            await pilot.pause()
            assert isinstance(app.screen, ComposeScreen)
            assert "$275" in app.messages[0].html
            assert "home-service pros" in app.messages[0].html

    asyncio.run(scenario())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
