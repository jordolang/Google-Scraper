"""Tests for school_config module."""

import re
import pytest

from school_config import (
    SUPPORTED_SPORTS,
    SEARCH_QUERY_TEMPLATES,
    SCHOOL_DOMAIN_PATTERNS,
    SCHOOL_TITLE_KEYWORDS,
    EXCLUDED_DOMAINS,
    ATHLETICS_PAGE_KEYWORDS,
    ATHLETICS_URL_PATTERNS,
    STAFF_TITLE_PATTERNS,
    GENERIC_EMAIL_PREFIXES,
    FUNDRAISER_CONFIG,
    SPORT_PITCHES,
    DEFAULT_PITCH,
    STATE_ABBREVIATIONS,
    ABBREV_TO_STATE,
    get_config,
)


class TestSupportedSports:
    def test_is_nonempty_tuple(self):
        assert isinstance(SUPPORTED_SPORTS, tuple)
        assert len(SUPPORTED_SPORTS) > 0

    def test_all_lowercase_strings(self):
        for sport in SUPPORTED_SPORTS:
            assert isinstance(sport, str)
            assert sport == sport.lower(), f"Sport '{sport}' should be lowercase"

    def test_contains_major_sports(self):
        major = {"football", "basketball", "baseball", "soccer", "volleyball"}
        for sport in major:
            assert sport in SUPPORTED_SPORTS, f"Missing major sport: {sport}"

    def test_no_duplicates(self):
        assert len(SUPPORTED_SPORTS) == len(set(SUPPORTED_SPORTS))


class TestSearchQueryTemplates:
    def test_has_required_keys(self):
        required = {"by_city", "by_city_coaches", "by_district", "by_k12_domain"}
        assert required.issubset(set(SEARCH_QUERY_TEMPLATES.keys()))

    def test_city_template_has_placeholders(self):
        template = SEARCH_QUERY_TEMPLATES["by_city"]
        assert "{city}" in template
        assert "{state}" in template

    def test_district_template_has_placeholders(self):
        template = SEARCH_QUERY_TEMPLATES["by_district"]
        assert "{district}" in template
        assert "{state}" in template

    def test_k12_template_has_state_abbrev(self):
        template = SEARCH_QUERY_TEMPLATES["by_k12_domain"]
        assert "{state_abbrev}" in template


class TestSchoolDetection:
    def test_domain_patterns_nonempty(self):
        assert len(SCHOOL_DOMAIN_PATTERNS) > 0

    def test_domain_patterns_include_k12(self):
        assert any(".k12." in p for p in SCHOOL_DOMAIN_PATTERNS)

    def test_domain_patterns_include_edu(self):
        assert any(".edu" in p for p in SCHOOL_DOMAIN_PATTERNS)

    def test_title_keywords_nonempty(self):
        assert len(SCHOOL_TITLE_KEYWORDS) > 0

    def test_excluded_domains_nonempty(self):
        assert len(EXCLUDED_DOMAINS) > 0

    def test_excluded_domains_include_common_sites(self):
        assert "niche.com" in EXCLUDED_DOMAINS
        assert "zillow.com" in EXCLUDED_DOMAINS
        assert "wikipedia.org" in EXCLUDED_DOMAINS


class TestAthleticsConfig:
    def test_page_keywords_nonempty(self):
        assert len(ATHLETICS_PAGE_KEYWORDS) > 0
        assert "athletics" in ATHLETICS_PAGE_KEYWORDS

    def test_url_patterns_nonempty(self):
        assert len(ATHLETICS_URL_PATTERNS) > 0
        assert any("/athletics" in p for p in ATHLETICS_URL_PATTERNS)


class TestStaffTitlePatterns:
    def test_has_required_roles(self):
        required = {"athletic_director", "head_coach", "assistant_coach"}
        assert required.issubset(set(STAFF_TITLE_PATTERNS.keys()))

    def test_patterns_are_valid_regex(self):
        for role, pattern in STAFF_TITLE_PATTERNS.items():
            try:
                re.compile(pattern)
            except re.error as e:
                pytest.fail(f"Invalid regex for {role}: {e}")

    def test_athletic_director_matches(self):
        pattern = re.compile(STAFF_TITLE_PATTERNS["athletic_director"])
        assert pattern.search("Athletic Director")
        assert pattern.search("Director of Athletics")

    def test_head_coach_matches(self):
        pattern = re.compile(STAFF_TITLE_PATTERNS["head_coach"])
        assert pattern.search("Head Coach")
        assert pattern.search("Varsity Coach")

    def test_assistant_coach_matches(self):
        pattern = re.compile(STAFF_TITLE_PATTERNS["assistant_coach"])
        assert pattern.search("Assistant Coach")
        assert pattern.search("JV Coach")


class TestGenericEmailPrefixes:
    def test_nonempty(self):
        assert len(GENERIC_EMAIL_PREFIXES) > 0

    def test_includes_common_generic(self):
        assert "info@" in GENERIC_EMAIL_PREFIXES
        assert "office@" in GENERIC_EMAIL_PREFIXES
        assert "admin@" in GENERIC_EMAIL_PREFIXES


class TestFundraiserConfig:
    def test_has_required_keys(self):
        required = {
            "product_name",
            "fundraiser_percentage",
            "min_order",
            "upfront_cost",
            "product_types",
        }
        assert required.issubset(set(FUNDRAISER_CONFIG.keys()))

    def test_product_name(self):
        assert FUNDRAISER_CONFIG["product_name"] == "Jose Madrid Salsa"

    def test_percentage_is_string(self):
        assert isinstance(FUNDRAISER_CONFIG["fundraiser_percentage"], str)
        assert "%" in FUNDRAISER_CONFIG["fundraiser_percentage"]

    def test_product_types_is_list(self):
        assert isinstance(FUNDRAISER_CONFIG["product_types"], list)
        assert len(FUNDRAISER_CONFIG["product_types"]) > 0


class TestSportPitches:
    def test_major_sports_have_pitches(self):
        for sport in ("football", "basketball", "baseball", "soccer"):
            assert sport in SPORT_PITCHES, f"Missing pitch for {sport}"

    def test_default_pitch_exists(self):
        assert DEFAULT_PITCH
        assert isinstance(DEFAULT_PITCH, str)


class TestStateAbbreviations:
    def test_has_50_states(self):
        assert len(STATE_ABBREVIATIONS) == 50

    def test_abbreviations_are_lowercase(self):
        for state, abbrev in STATE_ABBREVIATIONS.items():
            assert abbrev == abbrev.lower()
            assert len(abbrev) == 2

    def test_reverse_lookup(self):
        assert len(ABBREV_TO_STATE) == 50
        assert ABBREV_TO_STATE["oh"] == "Ohio"
        assert ABBREV_TO_STATE["tx"] == "Texas"


class TestGetConfig:
    def test_returns_dict(self):
        config = get_config()
        assert isinstance(config, dict)

    def test_has_essential_keys(self):
        config = get_config()
        essential = {
            "supported_sports",
            "fundraiser_config",
            "from_email",
            "template_path",
            "subject_line_templates",
            "sport_pitches",
        }
        assert essential.issubset(set(config.keys()))

    def test_sports_in_config(self):
        config = get_config()
        assert config["supported_sports"] == SUPPORTED_SPORTS
