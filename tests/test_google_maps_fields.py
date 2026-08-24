"""The columns a Google Maps scrape is contracted to produce.

The exports feed a mail merge, which maps every column by name: a field that
silently comes back empty is a merge field that renders blank in an email that
has already gone out. These tests pin the schema, the header spellings the
merge maps against, and the two extractions that have no DOM fallback left --
the plus code computed from the listing's own coordinates, and the website URL
pulled out of whichever attribute Maps happened to render it in.
"""

from __future__ import annotations

import csv

import pytest
from selenium.common.exceptions import NoSuchElementException

import data_store
from google_maps_scraper import (
    GoogleMapsScraper,
    clean_url,
    coords_from_url,
    plus_code,
)

#: What the email application maps, in the order it was asked for.
REQUIRED_COLUMNS = (
    "name", "rating", "reviews_count", "category", "address", "phone",
    "website", "plus_code", "hours", "url", "search_term", "search_location",
    "email", "contact_name", "scraped_phone", "phone_source",
    "emailed", "emailed_at", "emailed_to", "emailed_subject", "email_template",
)


# --------------------------------------------------------------- the schema

def test_listings_export_carries_every_mapped_column():
    assert tuple(data_store.LISTING_FIELDS) == REQUIRED_COLUMNS


def test_contacts_export_is_a_superset_of_the_listings_export():
    """The contact scan used to drop rating, reviews, plus code and hours."""
    missing = set(data_store.LISTING_FIELDS) - set(data_store.CONTACT_FIELDS)
    assert not missing


def test_a_scraped_row_has_a_slot_for_every_column(monkeypatch):
    monkeypatch.setattr(GoogleMapsScraper, "__init__", lambda self: None)
    scraper = GoogleMapsScraper()
    scraper.search_term, scraper.location = "Roofers", "Zanesville, OH"

    row = scraper._blank_record()

    assert set(row) == set(REQUIRED_COLUMNS)
    assert row["search_term"] == "Roofers"
    assert row["search_location"] == "Zanesville, OH"


# -------------------------------------------------------------- the headers

def test_every_column_has_the_header_the_merge_asked_for():
    assert data_store.header_label("name") == "Business Name"
    assert data_store.header_label("reviews_count") == "Reviews Count"
    assert data_store.header_label("plus_code") == "Plus Code"
    assert data_store.header_label("url") == "URL"


@pytest.mark.parametrize("header", ["Business Name", "business name", "name"])
def test_headers_map_back_to_one_field(header):
    assert data_store.field_for_header(header) == "name"


def test_friendly_headers_round_trip(tmp_path):
    """A merge-ready export still reads back into the rest of the pipeline."""
    row = {field: f"v-{field}" for field in data_store.LISTING_FIELDS}
    path = data_store.export_listings(
        [row], "Roofers", "Zanesville, OH", base=tmp_path,
        friendly_headers=True,
    )

    with open(path, newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[:4] == ["Business Name", "Rating", "Reviews Count", "Category"]
    assert "Plus Code" in header

    assert data_store.read_rows(path) == [row]


def test_a_friendly_export_stays_friendly_when_it_is_updated(tmp_path):
    """update_listings must not flip the headers out from under the merge."""
    path = data_store.export_listings(
        [{"name": "Acme Roofing"}], "Roofers", "Zanesville, OH",
        base=tmp_path, friendly_headers=True,
    )

    data_store.update_listings(path, {"acme roofing": {"email": "a@b.example"}})

    with open(path, newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[0] == "Business Name"
    assert data_store.read_rows(path)[0]["email"] == "a@b.example"


# ------------------------------------------------------------- the plus code

@pytest.mark.parametrize("latitude,longitude,expected", [
    # Reference vectors from google/open-location-code.
    (20.3701135, 2.7821815, "7FG49QCJ+2V"),
    (47.0000625, 8.0000625, "8FVC2222+22"),
    (-41.2730625, 174.7859375, "4VCPPQGP+Q9"),
    (-89.9999375, -179.9999375, "22222222+22"),
    (0.0, 0.0, "6FG22222+22"),
])
def test_plus_code_matches_the_reference_encoding(latitude, longitude, expected):
    assert plus_code(latitude, longitude) == expected


def test_plus_code_survives_the_poles_and_the_dateline():
    assert plus_code(90, 10) == "CFXGX2X2+X2"
    assert plus_code(0, 180) == plus_code(0, -180)


def test_plus_code_without_coordinates_is_empty_not_a_crash():
    assert plus_code(None, None) == ""
    assert plus_code("", "") == ""


@pytest.mark.parametrize("url,expected", [
    # The !3d/!4d pair is the pin; the @ segment is only the viewport centre,
    # so the pin wins when a URL carries both.
    ("https://www.google.com/maps/place/Acme/@39.1,-82.1,17z/"
     "data=!4m6!3m5!1s0x0!8m2!3d39.9403!4d-82.0132", (39.9403, -82.0132)),
    ("https://www.google.com/maps/place/Acme/@39.9403,-82.0132,17z",
     (39.9403, -82.0132)),
    ("https://www.google.com/maps/place/Acme", (None, None)),
    ("", (None, None)),
])
def test_coordinates_come_out_of_the_place_url(url, expected):
    assert coords_from_url(url) == expected


def test_a_listing_with_no_plus_code_row_still_gets_one():
    """Maps hides the row on plenty of listings; the URL still has the pin."""
    url = ("https://www.google.com/maps/place/Acme/@39.1,-82.1,17z/"
           "data=!4m6!3m5!1s0x0!8m2!3d47.0000625!4d8.0000625")

    class Panel:
        """A detail panel that renders no plus-code row at all."""

        current_url = url

        def find_element(self, *_args):
            raise NoSuchElementException()

    scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
    scraper.driver = Panel()

    assert scraper._extract_plus_code(url) == "8FVC2222+22"


# --------------------------------------------------------------- the website

@pytest.mark.parametrize("raw,expected", [
    ("https://acmeroofing.example/", "https://acmeroofing.example/"),
    ("acmeroofing.example", "https://acmeroofing.example"),
    ("//acmeroofing.example", "https://acmeroofing.example"),
    ("https://www.google.com/url?q=https://acmeroofing.example&sa=U",
     "https://acmeroofing.example"),
    ("", ""),
    ("Website", ""),  # an aria-label with no value in it
])
def test_website_values_are_normalised(raw, expected):
    assert clean_url(raw) == expected


# ------------------------------------------------- the whole panel, end to end

class FakeElement:
    """One node of a stand-in detail panel."""

    def __init__(self, text="", attrs=None, children=None, parent=None):
        self.text = text
        self._attrs = attrs or {}
        self._children = children or {}
        self._parent = parent

    def get_attribute(self, name):
        return self._attrs.get(name)

    def find_element(self, by, selector):
        if selector == "./..":
            if self._parent is None:
                raise NoSuchElementException(selector)
            return self._parent
        found = self._children.get(selector)
        if isinstance(found, list):
            found = found[0] if found else None
        if found is None:
            raise NoSuchElementException(selector)
        return found

    def find_elements(self, by, selector):
        found = self._children.get(selector, [])
        return found if isinstance(found, list) else [found]


class FakePanel:
    """A Google Maps place page with every row rendered."""

    current_url = ("https://www.google.com/maps/place/Bright+Spark+Electric/"
                   "@39.1,-82.1,17z/data=!4m6!3m5!1s0x0!8m2!3d47.0000625"
                   "!4d8.0000625")

    def __init__(self, nodes):
        self._nodes = nodes

    def find_element(self, by, selector):
        found = self._nodes.get(selector)
        if isinstance(found, list):
            found = found[0] if found else None
        if found is None:
            raise NoSuchElementException(selector)
        return found

    def find_elements(self, by, selector):
        found = self._nodes.get(selector, [])
        return found if isinstance(found, list) else [found]


@pytest.fixture
def panel():
    rating_row = FakeElement()
    rating = FakeElement(
        text="4.8", children={'span[aria-hidden="true"]': FakeElement("4.8")},
        parent=rating_row,
    )
    rating_row._children = {"span": [FakeElement("4.8"), FakeElement("(127)")]}

    return FakePanel({
        "h1.DUwDvf": FakeElement("Bright Spark Electric"),
        "div.F7nice": rating,
        "button.DkEaL": FakeElement("Electrician"),
        'button[data-item-id="address"]': FakeElement(
            attrs={"aria-label": "Address: 123 Main St, Zanesville, OH 43701"}),
        'button[data-item-id^="phone"]': FakeElement(
            attrs={"data-item-id": "phone:tel:+16145550142"}),
        'a[data-item-id="authority"]': FakeElement(
            attrs={"href": "https://brightspark.example/"}),
        'button[data-item-id="oloc"]': FakeElement(
            attrs={"aria-label": "Plus code: 2222+22 Zurich, Switzerland"}),
        '[aria-label*="Copy open hours" i]': [
            FakeElement(attrs={"aria-label":
                               "Monday, 8 AM to 5 PM, Copy open hours"}),
            FakeElement(attrs={"aria-label":
                               "Tuesday, Open 24 hours, Copy open hours"}),
        ],
    })


def _scraper(panel):
    scraper = GoogleMapsScraper.__new__(GoogleMapsScraper)
    scraper.driver = panel
    scraper.search_term, scraper.location = "Electricians", "Zanesville, OH"
    return scraper


def test_a_fully_rendered_panel_fills_every_mapped_column(panel):
    row = _scraper(panel)._extract_business_details()

    assert row["name"] == "Bright Spark Electric"
    assert row["rating"] == "4.8"
    assert row["reviews_count"] == "127"
    assert row["category"] == "Electrician"
    assert row["address"] == "123 Main St, Zanesville, OH 43701"
    assert row["phone"] == "(614) 555-0142"
    assert row["website"] == "https://brightspark.example/"
    assert row["plus_code"] == "2222+22 Zurich, Switzerland"
    assert row["hours"] == "Monday: 8 AM to 5 PM; Tuesday: Open 24 hours"
    assert row["url"] == FakePanel.current_url
    assert row["search_term"] == "Electricians"
    assert row["search_location"] == "Zanesville, OH"


def test_a_half_rendered_panel_falls_back_to_the_feed_card(panel):
    """Maps hydrates the panel halfway more often than it should."""
    for selector in ("h1.DUwDvf", "div.F7nice", "button.DkEaL",
                     'button[data-item-id="address"]',
                     'button[data-item-id^="phone"]',
                     'a[data-item-id="authority"]',
                     'button[data-item-id="oloc"]'):
        panel._nodes.pop(selector)

    row = _scraper(panel)._extract_business_details(card={
        "name": "Bright Spark Electric",
        "rating": "4.8",
        "reviews_count": "127",
        "category": "Electrician",
        "address": "123 Main St",
        "phone": "(614) 555-0142",
        "website": "https://brightspark.example",
    })

    assert row["name"] == "Bright Spark Electric"
    assert row["reviews_count"] == "127"
    assert row["website"] == "https://brightspark.example"
    # No plus-code row and no card value — computed from the URL's own pin.
    assert row["plus_code"] == "8FVC2222+22"


def test_the_coverage_report_counts_every_scraped_column(panel):
    scraper = _scraper(panel)
    scraper.businesses = [scraper._extract_business_details()]

    coverage = scraper.coverage()

    assert set(coverage) == {
        "name", "rating", "reviews_count", "category", "address",
        "phone", "website", "plus_code", "hours", "url",
    }
    assert all(hit == 1 for hit in coverage.values())


def test_the_contact_scan_reads_either_header_style(tmp_path):
    """The scan runs on the listings CSV, whichever way it was exported."""
    from contact_scraper import ContactScraper

    path = data_store.export_listings(
        [{"name": "Bright Spark Electric", "reviews_count": "127",
          "plus_code": "8FVC2222+22", "website": "https://brightspark.example"}],
        "Electricians", "Zanesville, OH", base=tmp_path, friendly_headers=True,
    )

    rows = ContactScraper.load_csv(None, path)

    assert rows[0]["name"] == "Bright Spark Electric"
    assert rows[0]["website"] == "https://brightspark.example"
    assert rows[0]["reviews_count"] == "127"
    assert rows[0]["plus_code"] == "8FVC2222+22"
