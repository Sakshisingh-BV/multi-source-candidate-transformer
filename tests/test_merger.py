"""Tests for src/merger.py"""

import unittest
from src.models import NormalizedRecord, SkillEntry
from src.merger import merge


def _csv_record(**kwargs) -> NormalizedRecord:
    defaults = dict(source_id="recruiter_csv", full_name=None, emails=[], phones=[],
                    location=None, links=None, headline=None, skills=[],
                    experience=[], education=[], years_experience=None)
    defaults.update(kwargs)
    return NormalizedRecord(**defaults)


def _notes_record(**kwargs) -> NormalizedRecord:
    defaults = dict(source_id="recruiter_notes", full_name=None, emails=[], phones=[],
                    location=None, links=None, headline=None, skills=[],
                    experience=[], education=[], years_experience=None)
    defaults.update(kwargs)
    return NormalizedRecord(**defaults)


class TestMergeScalars(unittest.TestCase):
    def test_csv_wins_over_notes_on_conflict(self):
        """CSV (priority 1) should win over notes (priority 2) for scalar fields."""
        csv = _csv_record(full_name="Sakshi Singh", headline="Software Engineer")
        notes = _notes_record(full_name="Sakshi S.", headline="Senior Software Developer")
        profile = merge([csv, notes])
        self.assertEqual(profile.full_name, "Sakshi Singh")
        self.assertEqual(profile.headline, "Software Engineer")

    def test_notes_fills_missing_scalar(self):
        """If CSV has no value, notes value should be used."""
        csv = _csv_record(full_name="Sakshi Singh")
        notes = _notes_record(years_experience=3.0)
        profile = merge([csv, notes])
        self.assertEqual(profile.years_experience, 3.0)

    def test_single_source_works(self):
        csv = _csv_record(full_name="Priya Mehta", emails=["priya@example.com"])
        profile = merge([csv])
        self.assertEqual(profile.full_name, "Priya Mehta")


class TestMergeLists(unittest.TestCase):
    def test_emails_union_across_sources(self):
        csv = _csv_record(emails=["sakshi.singh@email.com"])
        notes = _notes_record(emails=["sakshi.s@gmail.com"])
        profile = merge([csv, notes])
        self.assertIn("sakshi.singh@email.com", profile.emails)
        self.assertIn("sakshi.s@gmail.com", profile.emails)
        self.assertEqual(len(profile.emails), 2)

    def test_emails_deduplication(self):
        csv = _csv_record(emails=["same@email.com"])
        notes = _notes_record(emails=["same@email.com"])
        profile = merge([csv, notes])
        self.assertEqual(profile.emails.count("same@email.com"), 1)

    def test_phones_sorted_deterministically(self):
        csv = _csv_record(phones=["+919876543210"])
        notes = _notes_record(phones=["+919123456789"])
        profile = merge([csv, notes])
        self.assertEqual(profile.phones, sorted(profile.phones))


class TestMergeSkills(unittest.TestCase):
    def test_skill_from_both_sources_has_full_confidence(self):
        csv = _csv_record(skills=["python", "sql"])
        notes = _notes_record(skills=["python", "javascript"])
        profile = merge([csv, notes])
        python_skill = next(s for s in profile.skills if s.name == "python")
        self.assertEqual(python_skill.confidence, 1.0)
        self.assertIn("recruiter_csv", python_skill.sources)
        self.assertIn("recruiter_notes", python_skill.sources)

    def test_skill_from_one_source_has_half_confidence(self):
        csv = _csv_record(skills=["python"])
        notes = _notes_record(skills=["javascript"])
        profile = merge([csv, notes])
        js_skill = next(s for s in profile.skills if s.name == "javascript")
        self.assertEqual(js_skill.confidence, 0.5)

    def test_skill_union_no_duplicates(self):
        csv = _csv_record(skills=["python", "sql"])
        notes = _notes_record(skills=["python", "docker"])
        profile = merge([csv, notes])
        skill_names = [s.name for s in profile.skills]
        self.assertEqual(len(skill_names), len(set(skill_names)))


class TestMergeExperience(unittest.TestCase):
    def test_experience_deduplication_by_company_title(self):
        exp = [{"company": "TechNova", "title": "Engineer", "start": "2022-06", "end": None, "summary": None}]
        csv = _csv_record(experience=exp)
        notes = _notes_record(experience=exp)
        profile = merge([csv, notes])
        self.assertEqual(len(profile.experience), 1)

    def test_experience_union_different_roles(self):
        exp_csv = [{"company": "TechNova", "title": "Engineer", "start": "2022-06", "end": None, "summary": None}]
        exp_notes = [{"company": "WebStart", "title": "Intern", "start": "2021-01", "end": "2022-05", "summary": None}]
        csv = _csv_record(experience=exp_csv)
        notes = _notes_record(experience=exp_notes)
        profile = merge([csv, notes])
        self.assertEqual(len(profile.experience), 2)


class TestProvenance(unittest.TestCase):
    def test_provenance_records_full_name_source(self):
        csv = _csv_record(full_name="Sakshi Singh")
        profile = merge([csv])
        fields = [p.field for p in profile.provenance]
        self.assertIn("full_name", fields)

    def test_provenance_source_is_correct(self):
        csv = _csv_record(full_name="Sakshi Singh")
        profile = merge([csv])
        entry = next(p for p in profile.provenance if p.field == "full_name")
        self.assertEqual(entry.source, "recruiter_csv")


class TestOverallConfidence(unittest.TestCase):
    def test_empty_record_low_confidence(self):
        profile = merge([_csv_record()])
        self.assertLess(profile.overall_confidence, 0.5)

    def test_full_record_high_confidence(self):
        csv = _csv_record(
            full_name="Sakshi Singh",
            emails=["sakshi@email.com"],
            phones=["+919876543210"],
            location={"city": "Jaipur", "region": "RJ", "country": "IN"},
            headline="Engineer",
            skills=["python", "sql"],
            experience=[{"company": "X", "title": "Dev", "start": "2022-01", "end": None, "summary": None}],
            education=[{"institution": "RTU", "degree": "B.Tech", "field": "CS", "end_year": 2021}],
            years_experience=2.0,
            links={"linkedin": "https://linkedin.com/in/x", "github": None, "portfolio": None, "other": []},
        )
        profile = merge([csv])
        self.assertGreater(profile.overall_confidence, 0.8)


if __name__ == "__main__":
    unittest.main()
