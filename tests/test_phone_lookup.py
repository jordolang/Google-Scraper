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


# --------------------------------------------------------------------------- #
#  emails and the multi-source contact lookup
# --------------------------------------------------------------------------- #
def test_extract_emails_drops_directory_and_image_addresses():
    text = ("Reach us at Info@BrightSpark.com, listed by help@yellowpages.com "
            "and logo@2x.png, or info@brightspark.com again")
    assert phone_lookup.extract_emails(text) == ["info@brightspark.com"]


def test_same_business_ignores_suffixes_and_case():
    assert phone_lookup.same_business("Bright Spark Electric, LLC", "bright spark electric")
    assert not phone_lookup.same_business("Sparky's Pizza", "Bright Spark Electric")


def test_mentions_business_needs_half_the_distinctive_words():
    assert phone_lookup.mentions_business("Bright Spark — electricians in Zanesville",
                                          "Bright Spark Electric")
    assert not phone_lookup.mentions_business("Other Co electricians", "Bright Spark Electric")


def test_plausible_email_rules():
    name, site = "Bright Spark Electric", "https://www.brightspark.com/contact"
    assert phone_lookup.plausible_email("info@brightspark.com", name, site)
    assert phone_lookup.plausible_email("hello@brightsparkelectric.net", name)
    assert phone_lookup.plausible_email("brightspark614@gmail.com", name)
    assert not phone_lookup.plausible_email("someone@gmail.com", name, allow_freemail=False)
    assert not phone_lookup.plausible_email("info@chamberofcommerce.org", name, site)


def test_city_state_from_a_maps_address():
    assert phone_lookup.city_state("123 Main St, Zanesville, OH 43701") == "Zanesville, OH"
    assert phone_lookup.city_state("Somewhere") == "Somewhere"


def _contacts_lookup(**finders):
    lookup = _lookup_with_fake_driver()
    for source in phone_lookup.CONTACT_SOURCES:
        setattr(lookup, f"_{source}_contacts",
                mock.Mock(return_value=finders.get(source, {"phones": [], "emails": []})))
    return lookup


def test_find_contacts_takes_each_field_from_the_first_source_that_has_it():
    lookup = _contacts_lookup(
        yellowpages={"phones": ["(614) 555-0142"], "emails": []},
        bbb={"phones": ["(740) 555-0000"], "emails": []},
        duckduckgo={"phones": [], "emails": ["info@brightspark.com"]},
    )
    result = lookup.find_contacts("Bright Spark", "Zanesville, OH")
    assert result == {
        "phones": ["(614) 555-0142"], "phone_source": "yellowpages",
        "emails": ["info@brightspark.com"], "email_source": "duckduckgo",
    }
    # Both found by the third source, so the rest are never asked.
    lookup._facebook_contacts.assert_not_called()
    lookup._google_contacts.assert_not_called()


def test_find_contacts_only_looks_for_what_is_missing():
    lookup = _contacts_lookup(yellowpages={"phones": ["(614) 555-0142"], "emails": []})
    result = lookup.find_contacts("Bright Spark", need_phone=False)
    assert result["phones"] == [] and result["phone_source"] == ""


def test_duckduckgo_only_trusts_results_that_name_the_business(monkeypatch):
    monkeypatch.setattr(phone_lookup.time, "sleep", lambda _s: None)
    lookup = _lookup_with_fake_driver(elements=[
        mock.Mock(text="Bright Spark Electric · Zanesville · (740) 555-0142 · "
                       "brightspark@gmail.com"),
        mock.Mock(text="Other Electric Co (740) 555-9999 other@gmail.com"),
    ])
    found = lookup._duckduckgo_contacts("Bright Spark Electric", "Zanesville, OH", "")
    assert found == {"phones": ["(740) 555-0142"], "emails": ["brightspark@gmail.com"]}
    assert "html.duckduckgo.com" in lookup.driver.get.call_args[0][0]
