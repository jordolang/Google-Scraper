import asyncio
from pathlib import Path

from textual.widgets import Static

from tui.app import OutreachApp
from tui.pipeline import make_pipeline


def _seed(tmp_path: Path) -> None:
    (tmp_path / "google_maps_results_x.csv").write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n",
        encoding="utf-8",
    )


def test_call_screen_steps_and_logs_disposition(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    from tui.cockpit.call import CallScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CallScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            screen = app.screen
            # Begins on the brief; 'n' enters the script and advances.
            assert screen.business_index == 0
            await pilot.press("enter")  # start script from brief
            await pilot.pause()
            start_step = screen.step_index
            await pilot.press("n")
            await pilot.pause()
            assert screen.step_index == start_step + 1
            await pilot.press("p")
            await pilot.pause()
            assert screen.step_index == start_step
            # Mark outcome → disposition modal → pick booked.
            await pilot.press("m")
            await pilot.pause()
            app.screen.query_one("#disp-list").highlighted = 0  # booked
            await pilot.click("#disp-ok")
            await pilot.pause()
            assert app.session.disposition("acme_plumbing") == "booked"
    asyncio.run(scenario())


def test_call_screen_objection_modal_smoke(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    from tui.cockpit.call import CallScreen
    from tui.cockpit.modals import ObjectionModal

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CallScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("enter")  # start script from brief
            await pilot.pause()
            await pilot.press("o")  # open objections
            await pilot.pause()
            assert isinstance(app.screen, ObjectionModal)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, CallScreen)
    asyncio.run(scenario())


def test_call_screen_callback_modal_records_callback_disposition(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    from textual.widgets import Input
    from tui.cockpit.call import CallScreen
    from tui.cockpit.modals import CallbackModal

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CallScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("enter")  # start script from brief
            await pilot.pause()
            await pilot.press("c")  # log callback
            await pilot.pause()
            assert isinstance(app.screen, CallbackModal)
            app.screen.query_one("#cb-when", Input).value = "tomorrow 2pm"
            app.screen.query_one("#cb-notes", Input).value = "asked to call back after lunch"
            await pilot.click("#cb-ok")
            await pilot.pause()
            assert app.session.disposition("acme_plumbing") == "callback"
    asyncio.run(scenario())


def test_call_screen_completion_message_persists_after_timer_tick(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    from tui.cockpit.call import CallScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CallScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("enter")  # start script from brief
            await pilot.pause()
            await pilot.press("m")  # mark outcome
            await pilot.pause()
            app.screen.query_one("#disp-list").highlighted = 0  # booked
            await pilot.click("#disp-ok")
            await pilot.pause()
            # Queue is now complete (single business seeded). Let a full
            # timer interval elapse to make sure the stale _tick doesn't
            # clobber the completion message.
            await pilot.pause(1.2)
            panel = str(app.screen.query_one("#call-panel", Static).content)
            assert "Queue complete" in panel
    asyncio.run(scenario())


def test_call_screen_resume_from_brief_preserves_step(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    from tui.cockpit.call import CallScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CallScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            screen = app.screen
            await pilot.press("enter")  # start script from brief
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            resumed_step = screen.step_index
            assert resumed_step > 0
            await pilot.press("b")  # view brief mid-call
            await pilot.pause()
            assert screen._on_brief is True
            await pilot.press("n")  # resume
            await pilot.pause()
            assert screen.step_index == resumed_step
    asyncio.run(scenario())


def test_call_screen_skip_records_no_answer_disposition(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    from tui.cockpit.call import CallScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(CallScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("enter")  # start script from brief
            await pilot.pause()
            await pilot.press("s")  # skip
            await pilot.pause()
            assert app.session.disposition("acme_plumbing") == "no_answer"
    asyncio.run(scenario())
