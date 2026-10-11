"""Shared test fixtures.

Anything that scrapes or sends now exports to ``data/``.  Point that at a
throwaway directory for the whole suite so a test run never writes into the
repo's real data.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_SCRAPER_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"
