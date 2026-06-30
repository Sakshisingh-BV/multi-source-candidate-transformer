"""Tests for src/merger.py — covers all four documented edge cases."""

import unittest
from src.models import NormalizedRecord
from src.merger import merge, _has_useful_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv(**kwargs) -> NormalizedRecord:
    base = dict(source_id="recruiter_csv", full_name=None, emails=[], phones=[],
                location=None, links=None, headline=None, skills=[],
                experience=[], education=[], years_experience=None)
    base.update(kwargs)
    return NormalizedRecord(**base)


def _notes(**kwargs) -> NormalizedRecord:
    base = dict(source_id="recruiter_notes", full_name=None, emails=[], phones=[],
                location=None, links=None, headline=None, skills=[],
                experience=[], education=[], years_experience=None)
    base.update(kwargs)
    return NormalizedRecord(**base)


def _empty_record() -> NormalizedRecord:
    """Simulates what a failed extractor produces — all fields None/[]."""
    return _csv()


# ---------------------------------------------------------------------------
# Edge case 1: Conflicting scalar values → source-priority wins
# ---------------------------------------------------------------------------

class TestEdgeCase1ConflictingScalars(unittest.TestCase):
    def test_csv_name_wins_over_notes(self):
        profile = merge([_csv(full_name="Sakshi Singh"), _notes(full_name="Sakshi S.")])
        self.assertEqual(profile.full_name, "Sakshi Singh")

    def test_csv_headline_wins_over_notes(self):
        profile = merge([_csv(headline="Software Engineer"), _notes(headline="Senior Software Developer")])
        self.assertEqual(profile.headline, "Software Engineer")

    def test_provenance_records_winning_source(self):
        profile = merge([_csv(full_name="Sakshi Singh"), _notes(full_name="Sakshi S.")])
        entry = next(p for p in profile.provenance if p.field == "full_name")
        self.assertEqual(entry.source, "recruiter_csv")

    def test_notes_wins_when_csv_is_none(self):
        """If CSV has no value, notes is the winner — not a conflict but
        verifies priority ordering does not skip valid lower-priority data."""
        profile = merge([_csv(), _notes(headline="Senior Dev")])
        self.assertEqual(profile.headline, "Senior Dev")


# ---------------------------------------------------------------------------
# Edge case 2: Partial records completing each other
# ---------------------------------------------------------------------------

class TestEdgeCase2PartialCompletion(unittest.TestCase):
    def test_csv_name_plus_notes_links_produces_full_profile(self):
        csv = _csv(full_name="Sakshi Singh", emails=["sakshi@email.com"])
        notes = _notes(
            links={"linkedin": "https://linkedin.com/in/x", "github": None, "portfolio": None, "other": []},
            years_experience=3.0,
        )
        profile = merge([csv, notes])
        self.assertEqual(profile.full_name, "Sakshi Singh")
        self.assertIn("sakshi@email.com", profile.emails)
        self.assertIsNotNone(profile.links)
        self.assertEqual(profile.links["linkedin"], "https://linkedin.com/in/x")
        self.assertEqual(profile.years_experience, 3.0)

    def test_emails_union_from_both_sources(self):
        csv = _csv(emails=["sakshi.singh@email.com"])
        notes = _notes(emails=["sakshi.s@gmail.com"])
        profile = merge([csv, notes])
        self.assertIn("sakshi.singh@email.com", profile.emails)
        self.assertIn("sakshi.s@gmail.com", profile.emails)
        self.assertEqual(len(profile.emails), 2)

    def test_phones_deduplicated_when_same_across_sources(self):
        csv = _csv(phones=["+919876543210"])
        notes = _notes(phones=["+919876543210"])
        profile = merge([csv, notes])
        self.assertEqual(len(profile.phones), 1)

    def test_result_is_sorted_deterministically(self):
        csv = _csv(emails=["z@email.com"])
        notes = _notes(emails=["a@email.com"])
        profile = merge([csv, notes])
        self.assertEqual(profile.emails, sorted(profile.emails))


# ---------------------------------------------------------------------------
# Edge case 3: Missing / garbage source never crashes
# ---------------------------------------------------------------------------

class TestEdgeCase3GracefulDegradation(unittest.TestCase):
    def test_has_useful_data_false_for_empty_record(self):
        self.assertFalse(_has_useful_data(_empty_record()))

    def test_has_useful_data_true_for_record_with_name(self):
        self.assertTrue(_has_useful_data(_csv(full_name="Sakshi")))

    def test_empty_record_filtered_out_before_merge(self):
        """A failed extractor record alongside a good record should not
        pollute the result — the good record's data must survive."""
        good = _csv(full_name="Sakshi Singh", emails=["sakshi@email.com"])
        bad = _notes()  # all None/[] — simulates failed extraction
        profile = merge([good, bad])
        self.assertEqual(profile.full_name, "Sakshi Singh")
        self.assertIn("sakshi@email.com", profile.emails)

    def test_all_empty_records_returns_minimal_profile_not_crash(self):
        profile = merge([_empty_record()])
        self.assertIsNotNone(profile.candidate_id)
        self.assertEqual(profile.overall_confidence, 0.0)

    def test_raises_on_no_records_at_all(self):
        with self.assertRaises(ValueError):
            merge([])


# ---------------------------------------------------------------------------
# Edge case 4: Skill synonyms + confidence
# ---------------------------------------------------------------------------

class TestEdgeCase4SkillSynonyms(unittest.TestCase):
    def test_canonicalized_synonyms_merge_into_one_entry(self):
        """'JS' and 'javascript' both normalize to 'javascript' before reaching
        the merger, so they should appear as a single skill entry."""
        # Both already canonical — normalizer.normalize_skill() would have run.
        csv = _csv(skills=["javascript"])
        notes = _notes(skills=["javascript"])  # would have been "JS" before normalize
        profile = merge([csv, notes])
        js_entries = [s for s in profile.skills if s.name == "javascript"]
        self.assertEqual(len(js_entries), 1)

    def test_skill_mentioned_in_both_sources_has_confidence_1(self):
        csv = _csv(skills=["python", "sql"])
        notes = _notes(skills=["python", "javascript"])
        profile = merge([csv, notes])
        python = next(s for s in profile.skills if s.name == "python")
        self.assertEqual(python.confidence, 1.0)

    def test_skill_mentioned_in_one_source_has_half_confidence(self):
        csv = _csv(skills=["python"])
        notes = _notes(skills=["javascript"])
        profile = merge([csv, notes])
        js = next(s for s in profile.skills if s.name == "javascript")
        self.assertEqual(js.confidence, 0.5)

    def test_skills_sorted_confidence_desc_then_alpha(self):
        csv = _csv(skills=["python", "sql"])
        notes = _notes(skills=["python", "docker"])
        profile = merge([csv, notes])
        confidences = [s.confidence for s in profile.skills]
        # All high-confidence skills come before lower-confidence ones
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    def test_skill_sources_tracked_correctly(self):
        csv = _csv(skills=["python"])
        notes = _notes(skills=["python"])
        profile = merge([csv, notes])
        python = next(s for s in profile.skills if s.name == "python")
        self.assertIn("recruiter_csv", python.sources)
        self.assertIn("recruiter_notes", python.sources)


# ---------------------------------------------------------------------------
# Experience and education (union + dedup)
# ---------------------------------------------------------------------------

class TestExperienceEducation(unittest.TestCase):
    def test_experience_dedup_by_company_title(self):
        exp = [{"company": "TechNova", "title": "Engineer", "start": "2022-06", "end": None, "summary": None}]
        profile = merge([_csv(experience=exp), _notes(experience=exp)])
        self.assertEqual(len(profile.experience), 1)

    def test_experience_union_different_roles(self):
        e1 = [{"company": "TechNova", "title": "Engineer", "start": "2022-06", "end": None, "summary": None}]
        e2 = [{"company": "WebStart", "title": "Intern", "start": "2021-01", "end": "2022-05", "summary": None}]
        profile = merge([_csv(experience=e1), _notes(experience=e2)])
        self.assertEqual(len(profile.experience), 2)

    def test_education_dedup_by_institution_degree(self):
        edu = [{"institution": "RTU", "degree": "B.Tech", "field": "CS", "end_year": 2021}]
        profile = merge([_csv(education=edu), _notes(education=edu)])
        self.assertEqual(len(profile.education), 1)


# ---------------------------------------------------------------------------
# Overall confidence
# ---------------------------------------------------------------------------

class TestOverallConfidence(unittest.TestCase):
    def test_empty_record_confidence_is_zero(self):
        self.assertEqual(merge([_empty_record()]).overall_confidence, 0.0)

    def test_partial_record_confidence_between_0_and_1(self):
        profile = merge([_csv(full_name="Sakshi", emails=["s@e.com"])])
        self.assertGreater(profile.overall_confidence, 0.0)
        self.assertLess(profile.overall_confidence, 1.0)

    def test_full_record_confidence_is_1(self):
        rec = _csv(
            full_name="Sakshi Singh",
            emails=["s@e.com"],
            phones=["+919876543210"],
            location={"city": "Jaipur", "region": "RJ", "country": "IN"},
            headline="Engineer",
            skills=["python"],
            experience=[{"company": "X", "title": "Dev", "start": "2022-01", "end": None, "summary": None}],
            education=[{"institution": "RTU", "degree": "B.Tech", "field": "CS", "end_year": 2021}],
            years_experience=2.0,
            links={"linkedin": "https://li.com", "github": None, "portfolio": None, "other": []},
        )
        profile = merge([rec])
        self.assertEqual(profile.overall_confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
