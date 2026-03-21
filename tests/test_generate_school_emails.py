"""Tests for generate_school_emails module."""

import csv
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from generate_school_emails import SchoolEmailGenerator


@pytest.fixture
def template_path():
    """Path to the actual school email template"""
    path = Path(__file__).parent.parent / "school_email_template.html"
    if not path.exists():
        pytest.skip("school_email_template.html not found")
    return str(path)


@pytest.fixture
def generator(template_path, tmp_path):
    """Create a SchoolEmailGenerator with temp output dir"""
    return SchoolEmailGenerator(
        template_path=template_path,
        output_dir=str(tmp_path / "emails"),
        from_email="test@example.com",
        from_name="Test Sender",
    )


@pytest.fixture
def sample_contact():
    return {
        "contact_name": "John Smith",
        "title": "Head Coach",
        "sport": "Football",
        "email": "jsmith@lincoln.edu",
        "phone": "(614) 555-1234",
        "school_name": "Lincoln High School",
        "school_url": "https://lincoln.k12.oh.us",
        "district": "Columbus City",
        "city": "Columbus",
        "state": "Ohio",
    }


# ==================== Greeting Name ====================


class TestGenerateGreetingName:
    def test_with_full_name(self, generator):
        data = {"contact_name": "John Smith", "title": "Head Coach"}
        assert generator.generate_greeting_name(data) == "Coach Smith"

    def test_with_coach_prefix_name(self, generator):
        data = {"contact_name": "Coach Johnson", "title": "Head Coach"}
        assert generator.generate_greeting_name(data) == "Coach Johnson"

    def test_with_director_title(self, generator):
        data = {"contact_name": "Jane Doe", "title": "Athletic Director"}
        assert generator.generate_greeting_name(data) == "Jane Doe"

    def test_fallback_to_title(self, generator):
        data = {"contact_name": "", "title": "Head Coach"}
        assert generator.generate_greeting_name(data) == "Head Coach"

    def test_fallback_to_director(self, generator):
        data = {"contact_name": "", "title": "Athletic Director"}
        assert generator.generate_greeting_name(data) == "Athletic Director"

    def test_fallback_to_generic(self, generator):
        data = {"contact_name": "", "title": ""}
        assert generator.generate_greeting_name(data) == "Coaching Staff"

    def test_no_data(self, generator):
        assert generator.generate_greeting_name({}) == "Coaching Staff"


# ==================== Sport Pitch ====================


class TestGenerateSportPitch:
    def test_football_pitch(self, generator):
        pitch = generator.generate_sport_pitch("Football")
        assert "equipment" in pitch.lower() or "travel" in pitch.lower()

    def test_basketball_pitch(self, generator):
        pitch = generator.generate_sport_pitch("Basketball")
        assert "tournament" in pitch.lower() or "uniforms" in pitch.lower()

    def test_unknown_sport(self, generator):
        pitch = generator.generate_sport_pitch("Unknown")
        assert pitch  # Should return default pitch

    def test_empty_sport(self, generator):
        pitch = generator.generate_sport_pitch("")
        assert pitch  # Should return default pitch

    def test_none_sport(self, generator):
        pitch = generator.generate_sport_pitch(None)
        assert pitch  # Should return default pitch


# ==================== Subject Line ====================


class TestGenerateSubjectLine:
    def test_includes_school_name(self, generator, sample_contact):
        subject = generator.generate_subject_line(sample_contact)
        assert "Lincoln High School" in subject or "Football" in subject

    def test_handles_unknown_sport(self, generator):
        data = {"school_name": "Test HS", "sport": "Unknown", "contact_name": "Smith"}
        subject = generator.generate_subject_line(data)
        assert "Unknown" not in subject  # Should use "Athletics" instead

    def test_deterministic(self, generator, sample_contact):
        subject1 = generator.generate_subject_line(sample_contact)
        subject2 = generator.generate_subject_line(sample_contact)
        assert subject1 == subject2

    def test_different_contacts_may_differ(self, generator):
        # Different names should potentially get different subjects
        data1 = {"school_name": "School A", "sport": "Football", "contact_name": "Smith"}
        data2 = {"school_name": "School B", "sport": "Basketball", "contact_name": "Jones"}
        # Just verify both generate valid subjects
        s1 = generator.generate_subject_line(data1)
        s2 = generator.generate_subject_line(data2)
        assert s1  # Non-empty
        assert s2  # Non-empty


# ==================== Email Generation ====================


class TestGenerateEmail:
    def test_replaces_all_placeholders(self, generator, sample_contact):
        html, filename, email = generator.generate_email(sample_contact)

        assert "{{" not in html, f"Unresolved placeholder found in generated email"

    def test_returns_valid_filename(self, generator, sample_contact):
        html, filename, email = generator.generate_email(sample_contact)

        assert filename.endswith("_email.html")
        assert " " not in filename  # No spaces in filename

    def test_returns_recipient_email(self, generator, sample_contact):
        html, filename, email = generator.generate_email(sample_contact)

        assert email == "jsmith@lincoln.edu"

    def test_html_contains_school_name(self, generator, sample_contact):
        html, _, _ = generator.generate_email(sample_contact)

        assert "Lincoln High School" in html

    def test_html_contains_sport(self, generator, sample_contact):
        html, _, _ = generator.generate_email(sample_contact)

        assert "Football" in html

    def test_html_contains_fundraiser_percentage(self, generator, sample_contact):
        html, _, _ = generator.generate_email(sample_contact)

        assert "50%" in html

    def test_unknown_sport_becomes_athletics(self, generator):
        data = {
            "contact_name": "Coach",
            "title": "Coach",
            "sport": "Unknown",
            "email": "test@test.com",
            "school_name": "Test HS",
            "district": "",
            "city": "Test City",
            "state": "OH",
        }
        html, _, _ = generator.generate_email(data)

        assert "Athletics" in html

    def test_handles_empty_fields(self, generator):
        data = {
            "contact_name": "",
            "title": "",
            "sport": "",
            "email": "",
            "school_name": "",
            "district": "",
            "city": "",
            "state": "",
        }
        html, filename, email = generator.generate_email(data)
        # Should not crash, even with empty data
        assert html
        assert filename


# ==================== CSV Processing ====================


class TestProcessCsv:
    def _create_test_csv(self, rows, tmp_path):
        csv_path = tmp_path / "test_contacts.csv"
        fieldnames = [
            "contact_name", "title", "sport", "email", "phone",
            "school_name", "school_url", "district", "city", "state",
        ]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                full_row = {k: row.get(k, "") for k in fieldnames}
                writer.writerow(full_row)
        return str(csv_path)

    def test_generates_emails(self, generator, tmp_path):
        csv_path = self._create_test_csv(
            [
                {
                    "contact_name": "Coach Smith",
                    "title": "Head Coach",
                    "sport": "Football",
                    "email": "smith@school.edu",
                    "school_name": "Test HS",
                    "city": "Columbus",
                    "state": "OH",
                }
            ],
            tmp_path,
        )

        stats = generator.process_csv(csv_path, skip_no_email=True)

        assert stats["generated"] == 1
        assert stats["errors"] == 0

    def test_skips_no_email(self, generator, tmp_path):
        csv_path = self._create_test_csv(
            [
                {
                    "contact_name": "Coach Smith",
                    "sport": "Football",
                    "email": "",
                    "school_name": "Test HS",
                }
            ],
            tmp_path,
        )

        stats = generator.process_csv(csv_path, skip_no_email=True)

        assert stats["generated"] == 0
        assert stats["skipped_no_email"] == 1

    def test_includes_no_email_when_flag_set(self, generator, tmp_path):
        csv_path = self._create_test_csv(
            [
                {
                    "contact_name": "Coach Smith",
                    "sport": "Football",
                    "email": "",
                    "school_name": "Test HS",
                    "city": "Columbus",
                    "state": "OH",
                }
            ],
            tmp_path,
        )

        stats = generator.process_csv(csv_path, skip_no_email=False)

        assert stats["generated"] == 1

    def test_respects_limit(self, generator, tmp_path):
        rows = [
            {
                "contact_name": f"Coach {i}",
                "sport": "Football",
                "email": f"coach{i}@school.edu",
                "school_name": f"School {i}",
                "city": "Columbus",
                "state": "OH",
            }
            for i in range(5)
        ]
        csv_path = self._create_test_csv(rows, tmp_path)

        stats = generator.process_csv(csv_path, limit=2)

        assert stats["generated"] == 2

    def test_sports_filter(self, generator, tmp_path):
        csv_path = self._create_test_csv(
            [
                {
                    "contact_name": "Coach A",
                    "sport": "Football",
                    "email": "a@school.edu",
                    "school_name": "Test HS",
                    "city": "Columbus",
                    "state": "OH",
                },
                {
                    "contact_name": "Coach B",
                    "sport": "Basketball",
                    "email": "b@school.edu",
                    "school_name": "Test HS",
                    "city": "Columbus",
                    "state": "OH",
                },
            ],
            tmp_path,
        )

        stats = generator.process_csv(
            csv_path, sports_filter=["football"]
        )

        assert stats["generated"] == 1
        assert stats["skipped_sport_filter"] == 1

    def test_writes_summary_file(self, generator, tmp_path):
        csv_path = self._create_test_csv(
            [
                {
                    "contact_name": "Coach Smith",
                    "sport": "Football",
                    "email": "smith@school.edu",
                    "school_name": "Test HS",
                    "city": "Columbus",
                    "state": "OH",
                }
            ],
            tmp_path,
        )

        generator.process_csv(csv_path)

        summary_path = Path(generator.output_dir) / "_email_summary.txt"
        assert summary_path.exists()

        content = summary_path.read_text()
        assert "Business:" in content  # Compatible format with send_emails.py
        assert "Email:" in content
        assert "File:" in content

    def test_skips_no_name_no_email(self, generator, tmp_path):
        csv_path = self._create_test_csv(
            [{"contact_name": "", "email": "", "school_name": "Test HS"}],
            tmp_path,
        )

        stats = generator.process_csv(csv_path, skip_no_email=False)

        assert stats["skipped_no_name"] == 1


# ==================== Clean Text ====================


class TestCleanText:
    def test_strips_whitespace(self, generator):
        assert generator.clean_text("  hello  ") == "hello"

    def test_strips_quotes(self, generator):
        assert generator.clean_text('"hello"') == "hello"

    def test_collapses_spaces(self, generator):
        assert generator.clean_text("hello   world") == "hello world"

    def test_empty_string(self, generator):
        assert generator.clean_text("") == ""

    def test_none(self, generator):
        assert generator.clean_text(None) == ""
