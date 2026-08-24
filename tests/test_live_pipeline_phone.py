"""The live pipeline must keep the phone number the feed already gave it.

`GoogleMapsScraper.scrape_listings` harvests the search-result cards before
opening any place page, because the detail panel routinely hydrates only
halfway when reached by direct URL navigation and the phone row is among the
first things missing. `LivePipeline._scrape_with_progress` reimplements that
loop for the desktop app and the TUI so it can stream progress — and for a
while it reimplemented it without the harvest, which is why the app's Phone
column came up empty while the command-line scraper filled it in.

These drive the pipeline against a stub scraper that behaves like Maps on a
bad day: cards carry phone numbers, detail panels do not.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from tui.pipeline import LivePipeline

CARDS: Dict[str, Dict[str, str]] = {
    "https://maps.google.com/place/a": {
        "name": "Precision Roofing", "phone": "(740) 453-3649",
        "phone_e164": "+17404533649", "category": "Roofing contractor",
    },
    "https://maps.google.com/place/b": {
        "name": "Adamsville Gutters", "phone": "(614) 555-0142",
        "phone_e164": "+16145550142", "category": "Gutter service",
    },
}


class StubScraper:
    """A scraper whose detail panel never renders a phone number.

    Mirrors the real class closely enough for the pipeline: cards are the only
    place the number appears, exactly as on a half-hydrated Maps page.
    """

    def __init__(self, *, panel_hydrates: bool = True) -> None:
        self._cards: Dict[str, Dict[str, str]] = {}
        self.businesses: List[dict] = []
        self.harvested = False
        self.panel_hydrates = panel_hydrates
        self.wait = self
        self.driver = self

    # -- the bits the pipeline touches ------------------------------------
    def until(self, _condition):          # stands in for WebDriverWait.until
        return True

    def _harvest_cards(self):
        self.harvested = True
        self._cards = dict(CARDS)
        return self._cards

    def _collect_all_business_urls(self):
        return list(CARDS)

    def _scrape_one(self, url, card):
        """What the real one does: detail fields, every one falling back to
        the card."""
        detail = {"website": f"{url}.example", "address": "2333 Adamsville Rd"}
        if not self.panel_hydrates:
            detail = {}
        record = {"url": url, "name": "", "phone": "", "phone_e164": ""}
        record.update(detail)
        for key, value in (card or {}).items():
            if value and not record.get(key):
                record[key] = value
        return record


class BrokenHarvestScraper(StubScraper):
    """The feed refuses to give up its cards."""

    def _harvest_cards(self):
        raise RuntimeError("stale element reference")


class EmptyHarvestScraper(StubScraper):
    """The harvest works and finds nothing — what a card-markup change on
    Google's side looks like from in here."""

    def _harvest_cards(self):
        self.harvested = True
        return {}


@pytest.fixture
def pipeline(tmp_path):
    return LivePipeline(data_root=tmp_path)


def run(pipeline, scraper) -> List:
    collected: List = []
    pipeline._scrape_with_progress(scraper, 8, lambda _line: None, collected)
    return collected


class TestPhoneSurvives:
    def test_the_cards_are_harvested_before_anything_is_opened(self, pipeline):
        scraper = StubScraper()
        run(pipeline, scraper)
        assert scraper.harvested, (
            "the feed's cards were never read; the phone number only exists "
            "there when the detail panel half-renders")

    def test_every_business_keeps_its_phone_number(self, pipeline):
        businesses = run(pipeline, StubScraper())
        assert len(businesses) == 2
        assert [b.phone for b in businesses] == ["(740) 453-3649", "(614) 555-0142"]

    def test_the_phone_survives_a_panel_that_never_hydrates(self, pipeline):
        """The case this regressed on: no detail data at all, card only."""
        businesses = run(pipeline, StubScraper(panel_hydrates=False))
        assert [b.phone for b in businesses] == ["(740) 453-3649", "(614) 555-0142"]
        assert [b.name for b in businesses] == ["Precision Roofing", "Adamsville Gutters"]

    def test_details_still_come_through_when_the_panel_works(self, pipeline):
        businesses = run(pipeline, StubScraper())
        assert all(b.website for b in businesses)

    def test_the_scrape_is_recorded_on_the_scraper(self, pipeline):
        scraper = StubScraper()
        run(pipeline, scraper)
        assert len(scraper.businesses) == 2


class TestScrollBudget:
    def test_max_scrolls_reaches_the_search(self, tmp_path, monkeypatch):
        """The scroll budget decides how much feed exists to harvest at all."""
        seen = {}

        class RecordingScraper(StubScraper):
            def search(self, field, location="", max_scrolls=10):
                seen["max_scrolls"] = max_scrolls

            def close(self):
                pass

        scraper = RecordingScraper()
        monkeypatch.setattr("google_maps_scraper.GoogleMapsScraper",
                            lambda **_kwargs: scraper, raising=False)
        pipeline = LivePipeline(data_root=tmp_path)
        pipeline.search("Roofing", "Zanesville, OH", max_scrolls=17)
        assert seen["max_scrolls"] == 17


class TestHarvestFailuresAreVisible:
    """A silent harvest failure is the original bug wearing a disguise.

    The point of the fix is that the cards carry the phone number. If they
    never arrive, the run still produces rows — just without phone numbers —
    so the only thing standing between that and a silent regression is saying
    so out loud.
    """

    def collect_progress(self, pipeline, scraper) -> str:
        lines: List[str] = []
        pipeline._scrape_with_progress(scraper, 8, lines.append, [])
        return "\n".join(lines)

    def test_a_raising_harvest_is_reported(self, pipeline):
        output = self.collect_progress(pipeline, BrokenHarvestScraper())
        assert "phone numbers may be missing" in output
        assert "stale element reference" in output

    def test_a_raising_harvest_does_not_stop_the_run(self, pipeline):
        """Rows without phone numbers still beat no rows at all."""
        collected: List = []
        pipeline._scrape_with_progress(
            BrokenHarvestScraper(), 8, lambda _line: None, collected)
        assert len(collected) == 2

    def test_an_empty_harvest_is_reported(self, pipeline):
        """No exception, no cards — the failure mode that hides best."""
        output = self.collect_progress(pipeline, EmptyHarvestScraper())
        assert "produced no cards" in output

    def test_a_healthy_harvest_says_nothing_alarming(self, pipeline):
        output = self.collect_progress(pipeline, StubScraper())
        assert "⚠" not in output
