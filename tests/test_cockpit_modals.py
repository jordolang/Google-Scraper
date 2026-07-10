import asyncio

from textual.app import App

from tui.cockpit.modals import CallbackModal, DispositionModal


def test_disposition_modal_returns_choice_and_notes():
    results = []

    class Host(App):
        def on_mount(self):
            self.push_screen(DispositionModal(), lambda r: results.append(r))

    async def scenario():
        app = Host()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.screen.query_one("#disp-list").highlighted = 0  # "booked"
            app.screen.query_one("#disp-notes").value = "great call"
            await pilot.click("#disp-ok")
            await pilot.pause()
    asyncio.run(scenario())
    assert results == [("booked", "great call")]


def test_callback_modal_returns_when_and_notes():
    results = []

    class Host(App):
        def on_mount(self):
            self.push_screen(CallbackModal(), lambda r: results.append(r))

    async def scenario():
        app = Host()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.screen.query_one("#cb-when").value = "tomorrow 2pm"
            app.screen.query_one("#cb-notes").value = "asked to call back"
            await pilot.click("#cb-ok")
            await pilot.pause()
    asyncio.run(scenario())
    assert results == [("tomorrow 2pm", "asked to call back")]
