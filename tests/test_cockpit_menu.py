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


def test_menu_routes_to_sheet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tui.cockpit.menu import CockpitMenuScreen
    from tui.cockpit.sheet import SheetScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="cockpit")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.screen.query_one("#cockpit-menu").highlighted = 1  # "sheet"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, SheetScreen)

    asyncio.run(scenario())
