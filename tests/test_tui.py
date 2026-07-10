"""Tests for the interactive outreach TUI (``tui`` package).

These exercise the model/pipeline layer directly and drive the full Textual
app end-to-end in demo mode via an in-process pilot.  Everything runs headless
and offline — no browser, network, or SMTP credentials required.
"""

import asyncio

import pytest

from tui.models import Business, EmailMessage
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
        ContactsScreen,
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

            await pilot.click("#scan")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, ContactsScreen)

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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
