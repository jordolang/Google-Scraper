import asyncio

from tui.app import OutreachApp
from tui.pipeline import make_pipeline


def test_cockpit_menu_renders_three_options():
    from tui.cockpit.menu import CockpitMenuScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="cockpit")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, CockpitMenuScreen)
            menu = app.screen.query_one("#cockpit-menu")
            ids = [opt.id for opt in menu._options]  # Textual OptionList options
            assert ids == ["prep", "sheet", "call"]

    asyncio.run(scenario())
