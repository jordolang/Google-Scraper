"""Tests for school_sports_scraper module."""

import csv
import json
import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from school_sports_scraper import SchoolSportsScraper


@pytest.fixture
def mock_driver():
    """Create a mock Chrome WebDriver"""
    with patch("school_sports_scraper.webdriver.Chrome") as mock_chrome:
        driver = MagicMock()
        mock_chrome.return_value = driver
        driver.title = "Test High School - Home"
        driver.current_url = "https://test.k12.oh.us"
        yield driver


class TestBuildSearchQueries:
    def test_city_state_queries(self, mock_driver):
        scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)
        queries = scraper._build_search_queries("Columbus", "Ohio", "high school")

        assert len(queries) >= 3
        assert any("Columbus" in q for q in queries)
        assert any("Ohio" in q for q in queries)

    def test_with_district(self, mock_driver):
        scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)
        queries = scraper._build_search_queries(
            "Columbus", "Ohio", "high school", district="Columbus City Schools"
        )

        assert any("Columbus City Schools" in q for q in queries)

    def test_middle_school_queries(self, mock_driver):
        scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)
        queries = scraper._build_search_queries("Columbus", "Ohio", "middle school")

        assert any("middle school" in q.lower() for q in queries)

    def test_all_school_types(self, mock_driver):
        scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)
        queries = scraper._build_search_queries("Columbus", "Ohio", "all")

        # Should include both high school and middle school queries
        assert len(queries) >= 4

    def test_state_abbreviation_resolution(self, mock_driver):
        scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)
        queries = scraper._build_search_queries("Columbus", "Ohio", "high school")

        # k12 domain query should use state abbreviation
        k12_queries = [q for q in queries if "k12" in q]
        assert len(k12_queries) > 0
        assert any("oh" in q.lower() for q in k12_queries)


class TestIsSchoolWebsite:
    @pytest.fixture(autouse=True)
    def setup(self, mock_driver):
        self.scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)

    def test_k12_domain(self):
        assert self.scraper._is_school_website("https://columbus.k12.oh.us")

    def test_edu_domain(self):
        assert self.scraper._is_school_website("https://school.edu/athletics")

    def test_finalsite_domain(self):
        assert self.scraper._is_school_website("https://school.finalsite.com")

    def test_rejects_niche(self):
        assert not self.scraper._is_school_website("https://www.niche.com/k12/school")

    def test_rejects_zillow(self):
        assert not self.scraper._is_school_website("https://www.zillow.com/schools")

    def test_rejects_wikipedia(self):
        assert not self.scraper._is_school_website(
            "https://en.wikipedia.org/wiki/School"
        )

    def test_rejects_youtube(self):
        assert not self.scraper._is_school_website("https://www.youtube.com/watch")

    def test_title_keyword_match(self):
        assert self.scraper._is_school_website(
            "https://example.com", title="Lincoln High School"
        )

    def test_snippet_keyword_match(self):
        assert self.scraper._is_school_website(
            "https://example.com", snippet="Columbus City School District"
        )

    def test_rejects_empty_url(self):
        assert not self.scraper._is_school_website("")

    def test_rejects_none_url(self):
        assert not self.scraper._is_school_website(None)


class TestExtractSchoolName:
    @pytest.fixture(autouse=True)
    def setup(self, mock_driver):
        self.scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)
        self.scraper.driver = mock_driver

    def test_from_page_title(self):
        self.scraper.driver.title = "Lincoln High School - Home"
        result = {"title": "fallback", "snippet": ""}
        name = self.scraper._extract_school_name(result)
        assert name == "Lincoln High School"

    def test_cleans_home_suffix(self):
        self.scraper.driver.title = "Lincoln High School - Home"
        result = {"title": "fallback", "snippet": ""}
        name = self.scraper._extract_school_name(result)
        assert "Home" not in name

    def test_falls_back_to_search_title(self):
        self.scraper.driver.title = ""
        self.scraper.driver.find_element.side_effect = Exception("no h1")
        result = {"title": "Washington Middle School", "snippet": ""}
        name = self.scraper._extract_school_name(result)
        assert name == "Washington Middle School"


class TestDetectSchoolType:
    @pytest.fixture(autouse=True)
    def setup(self, mock_driver):
        self.scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)

    def test_high_school(self):
        assert self.scraper._detect_school_type("Lincoln High School") == "high school"

    def test_middle_school(self):
        assert (
            self.scraper._detect_school_type("Washington Middle School")
            == "middle school"
        )

    def test_elementary(self):
        assert (
            self.scraper._detect_school_type("Oak Elementary School")
            == "elementary school"
        )

    def test_default_to_high_school(self):
        assert self.scraper._detect_school_type("Some Academy") == "high school"

    def test_from_snippet(self):
        assert (
            self.scraper._detect_school_type("Academy", "a junior high school")
            == "middle school"
        )


class TestExtractDistrict:
    @pytest.fixture(autouse=True)
    def setup(self, mock_driver):
        self.scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)

    def test_from_k12_domain(self):
        result = self.scraper._extract_district("columbus.k12.oh.us", "Lincoln HS")
        assert result == "Columbus"

    def test_from_school_name(self):
        result = self.scraper._extract_district(
            "example.com", "Columbus City School District"
        )
        assert "Columbus City School District" in result

    def test_empty_when_not_found(self):
        result = self.scraper._extract_district("example.com", "Lincoln HS")
        assert result == ""


class TestDeduplicateSchools:
    @pytest.fixture(autouse=True)
    def setup(self, mock_driver):
        self.scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)

    def test_removes_duplicate_domains(self):
        results = [
            {"url": "https://school.k12.oh.us/page1", "title": "School A"},
            {"url": "https://school.k12.oh.us/page2", "title": "School A again"},
            {"url": "https://other.k12.oh.us/page1", "title": "School B"},
        ]
        unique = self.scraper._deduplicate_schools(results)
        assert len(unique) == 2

    def test_keeps_unique_domains(self):
        results = [
            {"url": "https://school1.k12.oh.us", "title": "A"},
            {"url": "https://school2.k12.oh.us", "title": "B"},
        ]
        unique = self.scraper._deduplicate_schools(results)
        assert len(unique) == 2

    def test_handles_empty_list(self):
        assert self.scraper._deduplicate_schools([]) == []


class TestSaveToCsv:
    @pytest.fixture(autouse=True)
    def setup(self, mock_driver):
        self.scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)
        self.scraper.schools = [
            {
                "school_name": "Test High School",
                "school_url": "https://test.k12.oh.us",
                "full_url": "https://test.k12.oh.us/home",
                "district": "Test District",
                "city": "Columbus",
                "state": "Ohio",
                "school_type": "high school",
                "scraped_at": "2026-03-21T10:00:00",
            }
        ]

    def test_saves_correct_columns(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            filename = f.name

        try:
            self.scraper.save_to_csv(filename)

            with open(filename, "r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 1
            assert rows[0]["school_name"] == "Test High School"
            assert rows[0]["city"] == "Columbus"
            assert "school_url" in rows[0]
        finally:
            os.unlink(filename)

    def test_empty_results(self):
        self.scraper.schools = []
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            filename = f.name

        try:
            result = self.scraper.save_to_csv(filename)
            assert result == filename
        finally:
            if os.path.exists(filename):
                os.unlink(filename)


class TestSaveToJson:
    @pytest.fixture(autouse=True)
    def setup(self, mock_driver):
        self.scraper = SchoolSportsScraper.__new__(SchoolSportsScraper)
        self.scraper.schools = [
            {
                "school_name": "Test High School",
                "school_url": "https://test.k12.oh.us",
                "city": "Columbus",
                "state": "Ohio",
            }
        ]

    def test_saves_valid_json(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            filename = f.name

        try:
            self.scraper.save_to_json(filename)

            with open(filename, "r") as f:
                data = json.load(f)

            assert len(data) == 1
            assert data[0]["school_name"] == "Test High School"
        finally:
            os.unlink(filename)
