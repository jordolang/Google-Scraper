"""Tests for the Google / Yellow Pages phone-number fallback.

The parsing is pure, so it is tested directly; the browser-driving parts are
exercised against a fake driver rather than a real Chrome.
"""

from unittest import mock

import phone_lookup
from phone_lookup import PhoneLookup, extract_phones, normalize


def test_normalize_accepts_common_formats():
    assert normalize("614-555-0142") == "(614) 555-0142"
    assert normalize("(614) 555.0142") == "(614) 555-0142"
    assert normalize("call us at 6145550142 today") == "(614) 555-0142"


def test_normalize_rejects_junk():
    assert normalize("") is None
    assert normalize("no digits here") is None
    assert normalize("111-111-1111") is None  # placeholder
    assert normalize("123456") is None


def test_extract_phones_dedupes_and_skips_toll_free():
    text = "Call (614) 555-0142 or 614-555-0142, support 800-555-0199, sales (740) 555-0177"
    assert extract_phones(text) == ["(614) 555-0142", "(740) 555-0177"]


def test_extract_phones_can_keep_toll_free():
    assert extract_phones("800-555-0199", allow_tollfree=True) == ["(800) 555-0199"]


def _lookup_with_fake_driver(page_text="", elements=()):
    """A PhoneLookup whose browser is a stub returning canned page content."""
    lookup = PhoneLookup.__new__(PhoneLookup)  # no Chrome
    body = mock.Mock(text=page_text)
    driver = mock.Mock()
    driver.find_element.return_value = body
    driver.find_elements.return_value = list(elements)
    lookup.driver = driver
    return lookup


def test_google_reads_the_number_off_the_results_page(monkeypatch):
    monkeypatch.setattr(phone_lookup.time, "sleep", lambda _s: None)
    lookup = _lookup_with_fake_driver(page_text="Bright Spark Electric · (614) 555-0142")
    assert lookup.google("Bright Spark Electric", "Zanesville, OH") == ["(614) 555-0142"]
    url = lookup.driver.get.call_args[0][0]
    assert url.startswith("https://www.google.com/search?q=")
    assert "Bright+Spark+Electric" in url


def test_yellowpages_prefers_the_phone_element(monkeypatch):
    monkeypatch.setattr(phone_lookup.time, "sleep", lambda _s: None)
    lookup = _lookup_with_fake_driver(
        page_text="unrelated listing (740) 555-9999",
        elements=[mock.Mock(text="(614) 555-0142")],
    )
    assert lookup.yellowpages("Bright Spark Electric", "Zanesville, OH") == ["(614) 555-0142"]
    url = lookup.driver.get.call_args[0][0]
    assert "yellowpages.com/search" in url
    assert "geo_location_terms=Zanesville%2C+OH" in url


def test_find_falls_through_to_the_next_source(monkeypatch):
    monkeypatch.setattr(phone_lookup.time, "sleep", lambda _s: None)
    lookup = _lookup_with_fake_driver()
    lookup.google = mock.Mock(return_value=[])
    lookup.yellowpages = mock.Mock(return_value=["(614) 555-0142"])

    assert lookup.find("Bright Spark", "Zanesville, OH") == {
        "phones": ["(614) 555-0142"],
        "source": "yellowpages",
    }
    lookup.google.assert_called_once()


def test_find_reports_nothing_when_no_source_has_a_number():
    lookup = _lookup_with_fake_driver()
    lookup.google = mock.Mock(return_value=[])
    lookup.yellowpages = mock.Mock(return_value=[])
    assert lookup.find("Ghost Co", "Nowhere") == {"phones": [], "source": ""}


def test_find_needs_a_name():
    lookup = _lookup_with_fake_driver()
    assert lookup.find("", "Zanesville") == {"phones": [], "source": ""}
