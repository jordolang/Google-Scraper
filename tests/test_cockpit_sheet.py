import asyncio
from pathlib import Path

from tui.app import OutreachApp
from tui.pipeline import make_pipeline


def _write_csv(tmp_path: Path) -> None:
    (tmp_path / "google_maps_results_x.csv").write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n"
        "Bob Electric,Electrician,(614) 555-3434,http://bob.example,4.2,30\n",
        encoding="utf-8",
    )


def test_sheet_populates_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_csv(tmp_path)
    from tui.cockpit.sheet import SheetScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(SheetScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.screen.query_one("#sheet-table")
            assert table.row_count == 2

    asyncio.run(scenario())


def test_sheet_empty_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tui.cockpit.sheet import SheetScreen

    async def scenario():
        app = OutreachApp(pipeline=make_pipeline(demo=True), demo=True, start="home")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(SheetScreen())
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            empty = app.screen.query_one("#sheet-empty")
            assert "No scraped data" in str(empty.content)

    asyncio.run(scenario())
