"""Tests for the data/ export layer and everything that reads it back.

Covers the on-disk layout (data/<term>/<location>/*.csv), the outreach log that
gets folded into the listings file, and the rule that an emailed business drops
out of the sales-call queue.
"""

import csv
from datetime import datetime
from pathlib import Path

import pytest

import data_store
from salescall.data_loader import load_businesses
from tui.models import Business
from tui.pipeline import DemoPipeline, make_pipeline


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------------------- #
#  paths and names
# --------------------------------------------------------------------------- #
def test_slugify_keeps_state_and_drops_punctuation():
    assert data_store.slugify("Zanesville, OH") == "Zanesville-OH"
    assert data_store.slugify("HVAC / Heating") == "HVAC-Heating"
    assert data_store.slugify("") == "unspecified"


def test_search_dir_is_term_then_location(tmp_path):
    directory = data_store.search_dir("Electricians", "Zanesville, OH", base=tmp_path)
    assert directory == tmp_path / "Electricians" / "Zanesville-OH"
    assert directory.is_dir()


def test_timestamped_name_shape():
    name = data_store.timestamped_name("listings", datetime(2026, 7, 13, 23, 9))
    assert name == "listings71326-1109pm.csv"


def test_data_root_follows_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_SCRAPER_DATA_DIR", str(tmp_path / "elsewhere"))
    assert data_store.data_root() == tmp_path / "elsewhere"


# --------------------------------------------------------------------------- #
#  exports
# --------------------------------------------------------------------------- #
def test_export_listings_writes_rows_under_the_search(tmp_path):
    path = data_store.export_listings(
        [{"name": "Bright Spark", "phone": "(614) 555-0142"}],
        "Electricians",
        "Zanesville, OH",
        base=tmp_path,
    )
    assert path.parent == tmp_path / "Electricians" / "Zanesville-OH"
    assert path.name.startswith("listings")

    (row,) = read_csv(path)
    assert row["name"] == "Bright Spark"
    # The search that produced the row is stamped onto it.
    assert row["search_term"] == "Electricians"
    assert row["search_location"] == "Zanesville, OH"


def test_export_returns_none_with_nothing_to_save(tmp_path):
    assert data_store.export_listings([], "Electricians", "Zanesville", base=tmp_path) is None


def test_second_export_in_the_same_minute_does_not_clobber(tmp_path):
    when = datetime(2026, 7, 13, 23, 9)
    first = data_store.write_rows(
        [{"name": "A"}], fields=data_store.LISTING_FIELDS, prefix="listings",
        search_term="Electricians", location="Zanesville", base=tmp_path, when=when,
    )
    second = data_store.write_rows(
        [{"name": "B"}], fields=data_store.LISTING_FIELDS, prefix="listings",
        search_term="Electricians", location="Zanesville", base=tmp_path, when=when,
    )
    assert first != second
    assert first.exists() and second.exists()


def test_update_listings_merges_contacts_and_outreach(tmp_path):
    path = data_store.export_listings(
        [{"name": "Bright Spark"}, {"name": "Volt Masters"}],
        "Electricians", "Zanesville", base=tmp_path,
    )
    data_store.update_listings(
        path,
        {
            data_store.row_key("Bright Spark"): {
                "email": "info@bright.example",
                "scraped_phone": "(614) 555-0142",
                **data_store.outreach_record("info@bright.example", "Hello"),
            }
        },
    )

    rows = {r["name"]: r for r in read_csv(path)}
    emailed = rows["Bright Spark"]
    assert emailed["email"] == "info@bright.example"
    assert emailed["emailed"] == "yes"
    assert emailed["emailed_to"] == "info@bright.example"
    assert emailed["email_template"] == data_store.STANDARD_EMAIL
    assert emailed["emailed_at"]
    assert data_store.was_emailed(emailed)

    # The untouched business stays exactly as it was.
    assert rows["Volt Masters"]["emailed"] == ""
    assert not data_store.was_emailed(rows["Volt Masters"])


# --------------------------------------------------------------------------- #
#  the demo pipeline exports the same way the live one does
# --------------------------------------------------------------------------- #
def test_pipeline_search_exports_listings(tmp_path):
    pipeline = DemoPipeline(data_root=tmp_path)
    businesses = pipeline.search("Electricians", "Zanesville, OH")

    path = pipeline.last_listings_csv
    assert path.parent == tmp_path / "Electricians" / "Zanesville-OH"
    assert len(read_csv(path)) == len(businesses)


def test_pipeline_scan_folds_contacts_into_the_listings_file(tmp_path):
    pipeline = DemoPipeline(data_root=tmp_path)
    businesses = pipeline.search("Electricians", "Zanesville, OH")
    pipeline.scrape_contacts(businesses)

    assert pipeline.last_contacts_csv.exists()
    rows = {r["name"]: r for r in read_csv(pipeline.last_listings_csv)}
    # Demo names follow the search term ("Electricians" -> "Electrician Pros"),
    # so read the expected address off the business rather than hardcoding it.
    first = businesses[0]
    assert rows[first.name]["email"] == first.primary_email
    assert first.primary_email.endswith("@electricianpros.example")


def test_pipeline_send_logs_the_contact_attempt(tmp_path):
    pipeline = DemoPipeline(data_root=tmp_path)
    businesses = pipeline.search("Electricians", "Zanesville, OH")
    pipeline.scrape_contacts(businesses)
    messages = [pipeline.build_message(b) for b in businesses if b.has_email]

    pipeline.send(messages, password="", dry_run=False)

    rows = {r["name"]: r for r in read_csv(pipeline.last_listings_csv)}
    emailed = rows[messages[0].business.name]
    assert emailed["emailed"] == "yes"
    assert emailed["emailed_to"] == messages[0].to_email
    assert emailed["email_template"] == data_store.STANDARD_EMAIL
    # A business we never emailed is left alone.
    never = next(b for b in businesses if not b.has_email)
    assert rows[never.name]["emailed"] == ""


def test_dry_run_does_not_log_an_outreach(tmp_path):
    pipeline = DemoPipeline(data_root=tmp_path)
    businesses = pipeline.search("Electricians", "Zanesville, OH")
    pipeline.scrape_contacts(businesses)
    messages = [pipeline.build_message(b) for b in businesses if b.has_email]

    pipeline.send(messages, password="", dry_run=True)

    assert not any(data_store.was_emailed(r) for r in read_csv(pipeline.last_listings_csv))


def test_demo_pipeline_exports_into_a_demo_subtree(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_SCRAPER_DATA_DIR", str(tmp_path))
    pipeline = make_pipeline(demo=True)
    pipeline.search("Electricians", "Zanesville, OH")
    # Sample rows must never mix with real scrapes.
    assert "_demo" in pipeline.last_listings_csv.parts


# --------------------------------------------------------------------------- #
#  phone lookup
# --------------------------------------------------------------------------- #
def test_phone_lookup_fills_missing_numbers_and_exports(tmp_path):
    pipeline = DemoPipeline(data_root=tmp_path)
    businesses = [
        Business(name="No Contact Co", search_term="Electricians", search_location="Zanesville"),
    ]
    pipeline.find_phones(businesses, sources=("yellowpages",))

    business = businesses[0]
    assert business.phones
    assert business.phone_source == "yellowpages"
    assert not business.needs_phone
    # The number reaches the CSV (and through it, the call script).
    (row,) = read_csv(pipeline.last_contacts_csv)
    assert row["scraped_phone"] == business.phones[0]
    assert row["phone_source"] == "yellowpages"


def test_phone_lookup_skips_businesses_that_already_have_a_number(tmp_path):
    pipeline = DemoPipeline(data_root=tmp_path)
    business = Business(name="Has Phone", phones=["(614) 555-0100"], search_term="Electricians")
    pipeline.find_phones([business])
    assert business.phone_source == ""  # untouched


# --------------------------------------------------------------------------- #
#  the call script reads data/ and skips emailed businesses
# --------------------------------------------------------------------------- #
def test_call_script_reads_nested_data_dir_and_drops_emailed(tmp_path):
    listings = data_store.export_listings(
        [
            {"name": "Bright Spark", "phone": "(614) 555-0142", "address": "1 Main St, Zanesville, OH"},
            {"name": "Volt Masters", "phone": "(614) 555-0199", "address": "2 Oak Ave, Zanesville, OH"},
        ],
        "Electricians", "Zanesville, OH", base=tmp_path / "data",
    )
    data_store.update_listings(
        listings,
        {data_store.row_key("Bright Spark"): data_store.outreach_record("info@bright.example")},
    )

    names = [b.name for b in load_businesses(tmp_path)]
    assert names == ["Volt Masters"]  # the emailed business is off the call script

    # ...but it is still there when you ask for it.
    all_names = [b.name for b in load_businesses(tmp_path, include_emailed=True)]
    assert sorted(all_names) == ["Bright Spark", "Volt Masters"]


def test_call_script_ignores_demo_exports(tmp_path):
    data_store.export_listings(
        [{"name": "Demo Biz", "phone": "(614) 555-0000"}],
        "Electricians", "Zanesville", base=tmp_path / "data" / "_demo",
    )
    assert load_businesses(tmp_path) == []
