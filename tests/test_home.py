import asyncio

from tui.app import OutreachApp
from tui.pipeline import make_pipeline
from tui.pipeline_screens import SearchScreen


def test_home_opens_on_home_and_routes_to_pipeline():
    from tui.home import HomeScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            # Select the first option (Scrape → Email) and activate it.
            app.screen.query_one("#home-menu").highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, SearchScreen)
            # Esc returns to Home (Home sits beneath).
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    asyncio.run(scenario())


def test_start_pipeline_lands_on_search():
    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="pipeline")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, SearchScreen)

    asyncio.run(scenario())
