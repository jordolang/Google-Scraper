import asyncio
from pathlib import Path

from tui.app import OutreachApp
from tui.pipeline import make_pipeline


def test_prep_runs_and_logs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "google_maps_results_x.csv").write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n",
        encoding="utf-8",
    )
    # Stub intel so no network is touched.
    import tui.cockpit.prep as prep_mod
    from salescall.models import WebsiteIntel
    monkeypatch.setattr(prep_mod, "analyze_business", lambda b: WebsiteIntel(reachable=False))

    from tui.cockpit.prep import PrepScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(PrepScreen())
            await pilot.pause()
            await pilot.click("#prep-go")
            await app.workers.wait_for_complete()
            await pilot.pause()
            log = app.screen.query_one("#prep-log")
            # RichLog stores written lines; assert something was logged.
            assert log.lines
    asyncio.run(scenario())
