"""Tests for school_contact_scraper module."""

import csv
import json
import os
import re
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from school_contact_scraper import SchoolContactScraper


@pytest.fixture
def mock_driver():
    """Create a mock Chrome WebDriver"""
    with patch("school_contact_scraper.webdriver.Chrome") as mock_chrome:
        driver = MagicMock()
        mock_chrome.return_value = driver
        driver.title = "Athletics - Test High School"
        driver.current_url = "https://test.k12.oh.us/athletics"
        driver.page_source = "<html><body></body></html>"
        yield driver


@pytest.fixture
def scraper(mock_driver):
    """Create a SchoolContactScraper with mocked driver"""
    s = SchoolContactScraper.__new__(SchoolContactScraper)
    s.driver = mock_driver
    s.wait = MagicMock()
    s.sports_filter = None
    s.roles_filter = None
    s.email_pattern = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )
    s.phone_pattern = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
    return s


@pytest.fixture
def school_data():
    return {
        "school_name": "Lincoln High School",
        "school_url": "https://lincoln.k12.oh.us",
        "district": "Columbus City",
        "city": "Columbus",
        "state": "Ohio",
    }


# ==================== Staff Table Extraction ====================


class TestExtractContactsFromStaffTable:
    def test_basic_table(self, scraper, school_data):
        html = """
        <html><body>
        <table>
            <tr><th>Name</th><th>Sport</th><th>Title</th><th>Email</th></tr>
            <tr><td>John Smith</td><td>Football</td><td>Head Coach</td><td>jsmith@school.edu</td></tr>
            <tr><td>Jane Doe</td><td>Basketball</td><td>Head Coach</td><td>jdoe@school.edu</td></tr>
        </table>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_staff_table(
            soup, school_data, "https://test.com/athletics"
        )

        assert len(contacts) == 2
        assert contacts[0]["contact_name"] == "John Smith"
        assert contacts[0]["sport"] == "Football"
        assert contacts[0]["email"] == "jsmith@school.edu"
        assert contacts[1]["contact_name"] == "Jane Doe"

    def test_table_with_mailto_links(self, scraper, school_data):
        html = """
        <html><body>
        <table>
            <tr><th>Coach</th><th>Sport</th><th>Contact</th></tr>
            <tr>
                <td>Bob Wilson</td>
                <td>Soccer</td>
                <td><a href="mailto:bwilson@school.edu">Email</a></td>
            </tr>
        </table>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_staff_table(
            soup, school_data, "https://test.com/athletics"
        )

        assert len(contacts) == 1
        assert contacts[0]["email"] == "bwilson@school.edu"

    def test_skips_non_staff_tables(self, scraper, school_data):
        html = """
        <html><body>
        <table>
            <tr><th>Date</th><th>Score</th><th>Opponent</th></tr>
            <tr><td>Jan 1</td><td>55-40</td><td>Rival HS</td></tr>
        </table>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_staff_table(
            soup, school_data, "https://test.com/athletics"
        )

        assert len(contacts) == 0

    def test_table_missing_columns(self, scraper, school_data):
        html = """
        <html><body>
        <table>
            <tr><th>Name</th><th>Email</th></tr>
            <tr><td>Coach Smith</td><td>smith@school.edu</td></tr>
        </table>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_staff_table(
            soup, school_data, "https://test.com/athletics"
        )

        assert len(contacts) == 1
        assert contacts[0]["email"] == "smith@school.edu"


# ==================== Staff Card Extraction ====================


class TestExtractContactsFromStaffCards:
    def test_staff_card_divs(self, scraper, school_data):
        html = """
        <html><body>
        <div class="staff-card">
            <h3>John Smith</h3>
            <div class="title">Head Football Coach</div>
            <a href="mailto:jsmith@school.edu">Email</a>
            <span>(614) 555-1234</span>
        </div>
        <div class="staff-card">
            <h3>Jane Doe</h3>
            <div class="title">Basketball Coach</div>
            <a href="mailto:jdoe@school.edu">Email</a>
        </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_staff_cards(
            soup, school_data, "https://test.com/athletics"
        )

        assert len(contacts) == 2
        assert contacts[0]["contact_name"] == "John Smith"
        assert contacts[0]["email"] == "jsmith@school.edu"
        assert contacts[0]["phone"] == "(614) 555-1234"

    def test_coach_card_divs(self, scraper, school_data):
        html = """
        <html><body>
        <div class="coach-card">
            <strong>Bob Wilson</strong>
            <span class="position">Varsity Soccer Coach</span>
            <a href="mailto:bwilson@school.edu">Contact</a>
        </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_staff_cards(
            soup, school_data, "https://test.com/athletics"
        )

        assert len(contacts) == 1
        assert contacts[0]["contact_name"] == "Bob Wilson"

    def test_no_matching_cards(self, scraper, school_data):
        html = "<html><body><div class='random'>No staff here</div></body></html>"
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_staff_cards(
            soup, school_data, "https://test.com/athletics"
        )

        assert len(contacts) == 0


# ==================== Text Block Extraction ====================


class TestExtractContactsFromTextBlocks:
    def test_coach_name_pattern(self, scraper, school_data):
        html = """
        <html><body>
        <h2>Football</h2>
        <p>Head Coach: John Smith - jsmith@school.edu</p>
        <p>Assistant Coach: Bob Jones - bjones@school.edu</p>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_text_blocks(
            soup, school_data, "https://test.com/athletics/football"
        )

        assert len(contacts) >= 1

    def test_no_coach_patterns(self, scraper, school_data):
        html = """
        <html><body>
        <p>Welcome to our school website. We have great programs.</p>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        contacts = scraper._extract_contacts_from_text_blocks(
            soup, school_data, "https://test.com"
        )

        assert len(contacts) == 0


# ==================== Sport Detection ====================


class TestDetectSportFromUrl:
    def test_football_in_url(self, scraper):
        assert scraper._detect_sport_from_url("/athletics/football/coaches") == "Football"

    def test_basketball_in_url(self, scraper):
        assert scraper._detect_sport_from_url("/athletics/basketball") == "Basketball"

    def test_track_and_field_in_url(self, scraper):
        assert scraper._detect_sport_from_url("/athletics/track-and-field") == "Track And Field"

    def test_unknown_url(self, scraper):
        assert scraper._detect_sport_from_url("/about/staff") == "Unknown"

    def test_empty_url(self, scraper):
        assert scraper._detect_sport_from_url("") == "Unknown"

    def test_none_url(self, scraper):
        assert scraper._detect_sport_from_url(None) == "Unknown"


class TestDetectSportFromText:
    def test_football(self, scraper):
        assert scraper._detect_sport_from_text("Varsity Football Season") == "Football"

    def test_basketball(self, scraper):
        assert scraper._detect_sport_from_text("Girls Basketball Team") == "Basketball"

    def test_unknown(self, scraper):
        assert scraper._detect_sport_from_text("Welcome to our school") == "Unknown"

    def test_empty(self, scraper):
        assert scraper._detect_sport_from_text("") == "Unknown"

    def test_none(self, scraper):
        assert scraper._detect_sport_from_text(None) == "Unknown"


class TestDetectSportFromContext:
    def test_url_takes_priority(self, scraper):
        result = scraper._detect_sport_from_context(
            "Basketball coaching staff",
            "https://school.edu/athletics/football/coaches",
        )
        assert result == "Football"

    def test_falls_back_to_text(self, scraper):
        result = scraper._detect_sport_from_context(
            "Basketball coaching staff",
            "https://school.edu/athletics/staff",
        )
        assert result == "Basketball"


# ==================== Email Extraction ====================


class TestExtractEmailsFromPage:
    def test_mailto_links(self, scraper):
        html = '<html><body><a href="mailto:coach@school.edu">Email</a></body></html>'
        soup = BeautifulSoup(html, "lxml")
        emails = scraper._extract_emails_from_page(soup, html)

        assert "coach@school.edu" in emails

    def test_filters_generic_emails(self, scraper):
        html = '<html><body><a href="mailto:info@school.edu">Email</a></body></html>'
        soup = BeautifulSoup(html, "lxml")
        emails = scraper._extract_emails_from_page(soup, html)

        assert "info@school.edu" not in emails

    def test_regex_fallback(self, scraper):
        html = "<html><body><p>Contact jsmith@school.edu for info</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        emails = scraper._extract_emails_from_page(soup, html)

        assert "jsmith@school.edu" in emails

    def test_filters_image_emails(self, scraper):
        html = "<html><body><p>image123@test.jpg</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        emails = scraper._extract_emails_from_page(soup, html)

        assert len(emails) == 0


class TestIsPersonalEmail:
    def test_personal_email(self, scraper):
        assert scraper._is_personal_email("jsmith@school.edu")

    def test_rejects_info(self, scraper):
        assert not scraper._is_personal_email("info@school.edu")

    def test_rejects_office(self, scraper):
        assert not scraper._is_personal_email("office@school.edu")

    def test_rejects_admin(self, scraper):
        assert not scraper._is_personal_email("admin@school.edu")

    def test_rejects_empty(self, scraper):
        assert not scraper._is_personal_email("")

    def test_rejects_none(self, scraper):
        assert not scraper._is_personal_email(None)

    def test_rejects_no_at(self, scraper):
        assert not scraper._is_personal_email("notanemail")

    def test_rejects_image_extension(self, scraper):
        assert not scraper._is_personal_email("file@test.jpg")

    def test_rejects_example_domain(self, scraper):
        assert not scraper._is_personal_email("user@example.com")


# ==================== Name and Title Parsing ====================


class TestParseNameAndTitle:
    def test_head_coach_colon_pattern(self, scraper):
        name, title = scraper._parse_name_and_title("Head Coach: John Smith")
        assert "John Smith" in name
        assert "Head Coach" in title

    def test_name_comma_title(self, scraper):
        name, title = scraper._parse_name_and_title("John Smith, Head Coach")
        assert name == "John Smith"
        assert title == "Head Coach"

    def test_athletic_director(self, scraper):
        name, title = scraper._parse_name_and_title("Athletic Director Jane Doe")
        assert "Jane Doe" in name
        assert "Athletic Director" in title

    def test_empty_string(self, scraper):
        name, title = scraper._parse_name_and_title("")
        assert name == ""
        assert title == ""

    def test_none_input(self, scraper):
        name, title = scraper._parse_name_and_title(None)
        assert name == ""
        assert title == ""


# ==================== Deduplication ====================


class TestDeduplicateContacts:
    def test_removes_duplicate_emails(self, scraper):
        contacts = [
            {"contact_name": "John Smith", "email": "jsmith@school.edu", "school_name": "Test HS"},
            {"contact_name": "John Smith", "email": "jsmith@school.edu", "school_name": "Test HS"},
        ]
        unique = scraper._deduplicate_contacts(contacts)
        assert len(unique) == 1

    def test_removes_duplicate_names(self, scraper):
        contacts = [
            {"contact_name": "John Smith", "email": "", "school_name": "Test HS"},
            {"contact_name": "John Smith", "email": "", "school_name": "Test HS"},
        ]
        unique = scraper._deduplicate_contacts(contacts)
        assert len(unique) == 1

    def test_keeps_different_contacts(self, scraper):
        contacts = [
            {"contact_name": "John Smith", "email": "jsmith@school.edu", "school_name": "Test HS"},
            {"contact_name": "Jane Doe", "email": "jdoe@school.edu", "school_name": "Test HS"},
        ]
        unique = scraper._deduplicate_contacts(contacts)
        assert len(unique) == 2

    def test_skips_no_identifier(self, scraper):
        contacts = [
            {"contact_name": "", "email": "", "school_name": "Test HS"},
        ]
        unique = scraper._deduplicate_contacts(contacts)
        assert len(unique) == 0


# ==================== Build Contact ====================


class TestBuildContact:
    def test_builds_complete_contact(self, scraper, school_data):
        contact = scraper._build_contact(
            "John Smith", "Head Coach", "Football",
            "jsmith@school.edu", "(614) 555-1234", school_data
        )

        assert contact["contact_name"] == "John Smith"
        assert contact["title"] == "Head Coach"
        assert contact["sport"] == "Football"
        assert contact["email"] == "jsmith@school.edu"
        assert contact["phone"] == "(614) 555-1234"
        assert contact["school_name"] == "Lincoln High School"
        assert contact["city"] == "Columbus"

    def test_handles_empty_values(self, scraper, school_data):
        contact = scraper._build_contact("", "", "", "", "", school_data)

        assert contact["contact_name"] == ""
        assert contact["sport"] == "Unknown"
        assert contact["school_name"] == "Lincoln High School"


# ==================== CSV Output ====================


class TestSaveToCsv:
    def test_saves_correct_columns(self, scraper):
        results = [
            {
                "contact_name": "John Smith",
                "title": "Head Coach",
                "sport": "Football",
                "email": "jsmith@school.edu",
                "phone": "(614) 555-1234",
                "school_name": "Test HS",
                "school_url": "https://test.k12.oh.us",
                "district": "Test District",
                "city": "Columbus",
                "state": "Ohio",
            }
        ]

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            filename = f.name

        try:
            scraper.save_to_csv(results, filename)

            with open(filename, "r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            assert len(rows) == 1
            assert rows[0]["contact_name"] == "John Smith"
            assert rows[0]["sport"] == "Football"
            assert rows[0]["email"] == "jsmith@school.edu"
        finally:
            os.unlink(filename)

    def test_empty_results(self, scraper):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            filename = f.name

        try:
            result = scraper.save_to_csv([], filename)
            assert result == filename
        finally:
            if os.path.exists(filename):
                os.unlink(filename)
