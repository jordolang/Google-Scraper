from pathlib import Path

from tui.cockpit import data


def test_empty_dir_returns_empty_queue(tmp_path: Path):
    assert data.has_scraped_data(str(tmp_path)) is False
    assert data.load_queue(str(tmp_path)) == []


def test_loads_queue_from_results_csv(tmp_path: Path):
    csv = tmp_path / "google_maps_results_test.csv"
    csv.write_text(
        "name,category,phone,website,rating,reviews_count\n"
        "Acme Plumbing,Plumber,(614) 555-1212,,4.8,120\n"
        "Bob Electric,Electrician,(614) 555-3434,http://bob.example,4.2,30\n",
        encoding="utf-8",
    )
    assert data.has_scraped_data(str(tmp_path)) is True
    queue = data.load_queue(str(tmp_path))
    assert len(queue) == 2
    assert queue[0].business.name in {"Acme Plumbing", "Bob Electric"}
