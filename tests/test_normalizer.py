"""Tests for src/normalizer.py — individual helpers + full normalize()."""

import unittest
from src.models import RawRecord
from src.normalizer import (
    normalize,
    normalize_email,
    normalize_phone,
    normalize_skill,
    normalize_country,
    normalize_date,
)


class TestNormalizeEmail(unittest.TestCase):
    def test_lowercases_and_strips(self):
        self.assertEqual(normalize_email("  Sakshi@Email.COM  "), "sakshi@email.com")

    def test_valid_email_returned(self):
        self.assertEqual(normalize_email("user@example.in"), "user@example.in")

    def test_invalid_email_returns_none(self):
        self.assertIsNone(normalize_email("not-an-email"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(normalize_email(""))


class TestNormalizePhone(unittest.TestCase):
    def test_indian_number_to_e164(self):
        self.assertEqual(normalize_phone("+91 98765 43210"), "+919876543210")

    def test_number_with_dashes(self):
        self.assertEqual(normalize_phone("+91-91234-56789"), "+919123456789")

    def test_invalid_number_returns_none(self):
        self.assertIsNone(normalize_phone("12345"))

    def test_empty_returns_none(self):
        self.assertIsNone(normalize_phone(""))


class TestNormalizeSkill(unittest.TestCase):
    def test_synonym_js_to_javascript(self):
        self.assertEqual(normalize_skill("JS"), "javascript")

    def test_synonym_ml_to_machine_learning(self):
        self.assertEqual(normalize_skill("ML"), "machine learning")

    def test_synonym_react_js(self):
        self.assertEqual(normalize_skill("React.js"), "react")

    def test_unknown_skill_lowercased(self):
        self.assertEqual(normalize_skill("FastAPI"), "fastapi")

    def test_canonical_passthrough(self):
        self.assertEqual(normalize_skill("python"), "python")


class TestNormalizeCountry(unittest.TestCase):
    def test_india_to_IN(self):
        self.assertEqual(normalize_country("India"), "IN")

    def test_usa_to_US(self):
        self.assertEqual(normalize_country("USA"), "US")

    def test_united_states_to_US(self):
        self.assertEqual(normalize_country("United States"), "US")

    def test_unknown_returns_none(self):
        self.assertIsNone(normalize_country("Narnia"))

    def test_empty_returns_none(self):
        self.assertIsNone(normalize_country(""))


class TestNormalizeDate(unittest.TestCase):
    def test_iso_date(self):
        self.assertEqual(normalize_date("2022-06-01"), "2022-06")

    def test_human_readable(self):
        self.assertEqual(normalize_date("June 2022"), "2022-06")

    def test_year_month_already_formatted(self):
        self.assertEqual(normalize_date("2021-03"), "2021-03")

    def test_garbage_returns_none(self):
        self.assertIsNone(normalize_date("not a date"))

    def test_empty_returns_none(self):
        self.assertIsNone(normalize_date(""))


class TestNormalizeRawRecord(unittest.TestCase):
    def _make_csv_record(self):
        return RawRecord(
            source_id="recruiter_csv",
            source_type="structured",
            data={
                "full_name": "Sakshi Singh",
                "email": "Sakshi.Singh@Email.COM",
                "phone": "+91 98765 43210",
                "title": "Software Engineer",
                "skills": "Python;JS;ML;Docker",
                "location": "Jaipur, Rajasthan, India",
            },
        )

    def test_name_preserved(self):
        nr = normalize(self._make_csv_record())
        self.assertEqual(nr.full_name, "Sakshi Singh")

    def test_email_normalized(self):
        nr = normalize(self._make_csv_record())
        self.assertIn("sakshi.singh@email.com", nr.emails)

    def test_phone_e164(self):
        nr = normalize(self._make_csv_record())
        self.assertIn("+919876543210", nr.phones)

    def test_skills_canonicalized(self):
        nr = normalize(self._make_csv_record())
        self.assertIn("javascript", nr.skills)
        self.assertIn("machine learning", nr.skills)
        self.assertIn("python", nr.skills)

    def test_location_country_iso(self):
        nr = normalize(self._make_csv_record())
        self.assertEqual(nr.location["country"], "IN")

    def test_missing_file_does_not_raise(self):
        """Graceful degradation: garbage data must not crash normalize()."""
        raw = RawRecord(
            source_id="recruiter_csv",
            source_type="structured",
            data={},
            errors=["File not found: missing.csv"],
        )
        nr = normalize(raw)
        self.assertIsNone(nr.full_name)
        self.assertEqual(nr.emails, [])


if __name__ == "__main__":
    unittest.main()
