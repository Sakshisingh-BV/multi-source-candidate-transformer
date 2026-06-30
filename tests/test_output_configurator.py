"""Tests for src/output_configurator.py"""

import unittest
from src.models import CanonicalProfile, SkillEntry, ProvenanceEntry
from src.output_configurator import project, resolve_path, handle_missing, _OMIT


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _make_profile(**kwargs) -> CanonicalProfile:
    defaults = dict(
        candidate_id="test-001",
        full_name="Sakshi Singh",
        emails=["sakshi.singh@email.com", "sakshi.s@gmail.com"],
        phones=["+919876543210"],
        location={"city": "Jaipur", "region": "Rajasthan", "country": "IN"},
        links={"linkedin": "https://linkedin.com/in/sakshisingh", "github": "https://github.com/sakshisingh", "portfolio": None, "other": []},
        headline="Software Engineer",
        years_experience=3.0,
        skills=[
            SkillEntry(name="python", confidence=1.0, sources=["recruiter_csv", "recruiter_notes"]),
            SkillEntry(name="javascript", confidence=0.5, sources=["recruiter_notes"]),
        ],
        experience=[{"company": "TechNova", "title": "Engineer", "start": "2022-06", "end": None, "summary": None}],
        education=[{"institution": "RTU", "degree": "B.Tech", "field": "CS", "end_year": 2021}],
        provenance=[ProvenanceEntry(field="full_name", source="recruiter_csv", method="direct")],
        overall_confidence=0.9,
    )
    defaults.update(kwargs)
    return CanonicalProfile(**defaults)


PROFILE = _make_profile()


# ---------------------------------------------------------------------------
# resolve_path tests
# ---------------------------------------------------------------------------

class TestResolvePath(unittest.TestCase):
    def setUp(self):
        self.d = PROFILE.model_dump()

    def test_simple_path_string(self):
        self.assertEqual(resolve_path(self.d, "full_name"), "Sakshi Singh")

    def test_simple_path_number(self):
        self.assertEqual(resolve_path(self.d, "years_experience"), 3.0)

    def test_simple_path_missing_key_returns_none(self):
        self.assertIsNone(resolve_path(self.d, "nonexistent"))

    def test_array_index_first_element(self):
        self.assertEqual(resolve_path(self.d, "emails[0]"), "sakshi.singh@email.com")

    def test_array_index_second_element(self):
        self.assertEqual(resolve_path(self.d, "emails[1]"), "sakshi.s@gmail.com")

    def test_array_index_out_of_range_returns_none(self):
        self.assertIsNone(resolve_path(self.d, "emails[99]"))

    def test_array_index_on_empty_list_returns_none(self):
        d = PROFILE.model_dump()
        d["phones"] = []
        self.assertIsNone(resolve_path(d, "phones[0]"))

    def test_array_map_skills_name(self):
        result = resolve_path(self.d, "skills[].name")
        self.assertIsInstance(result, list)
        self.assertIn("python", result)
        self.assertIn("javascript", result)

    def test_array_map_returns_only_requested_field(self):
        result = resolve_path(self.d, "skills[].name")
        for item in result:
            self.assertIsInstance(item, str)

    def test_array_map_on_empty_list_returns_none(self):
        d = PROFILE.model_dump()
        d["skills"] = []
        self.assertIsNone(resolve_path(d, "skills[].name"))


# ---------------------------------------------------------------------------
# handle_missing tests
# ---------------------------------------------------------------------------

class TestHandleMissing(unittest.TestCase):
    def test_null_policy_returns_none(self):
        self.assertIsNone(handle_missing("null"))

    def test_omit_policy_returns_omit_sentinel(self):
        self.assertIs(handle_missing("omit"), _OMIT)

    def test_unknown_policy_defaults_to_none(self):
        self.assertIsNone(handle_missing("unknown"))


# ---------------------------------------------------------------------------
# project() — field selection
# ---------------------------------------------------------------------------

class TestProjectFieldSelection(unittest.TestCase):
    def _config(self, fields, **kwargs):
        return {"fields": fields, "on_missing": "null", **kwargs}

    def test_only_requested_fields_in_output(self):
        config = self._config([
            {"path": "full_name", "type": "string"},
            {"path": "emails",    "type": "string[]"},
        ])
        out = project(PROFILE, config)
        self.assertIn("full_name", out)
        self.assertIn("emails", out)
        self.assertNotIn("headline", out)
        self.assertNotIn("skills", out)

    def test_field_renaming_via_from(self):
        """'from': 'emails[0]' should appear under 'path': 'primary_email'."""
        config = self._config([{"path": "primary_email", "from": "emails[0]", "type": "string"}])
        out = project(PROFILE, config)
        self.assertIn("primary_email", out)
        self.assertEqual(out["primary_email"], "sakshi.singh@email.com")
        self.assertNotIn("emails", out)

    def test_skills_name_array_mapping(self):
        config = self._config([{"path": "skills", "from": "skills[].name", "type": "string[]"}])
        out = project(PROFILE, config)
        self.assertIsInstance(out["skills"], list)
        self.assertIn("python", out["skills"])

    def test_phone_index_access(self):
        config = self._config([{"path": "phone", "from": "phones[0]", "type": "string"}])
        out = project(PROFILE, config)
        self.assertEqual(out["phone"], "+919876543210")


# ---------------------------------------------------------------------------
# project() — on_missing behaviour
# ---------------------------------------------------------------------------

class TestProjectOnMissing(unittest.TestCase):
    def test_on_missing_null_includes_key_with_none(self):
        profile = _make_profile(headline=None)
        config = {"fields": [{"path": "headline", "type": "string"}], "on_missing": "null"}
        out = project(profile, config)
        self.assertIn("headline", out)
        self.assertIsNone(out["headline"])

    def test_on_missing_omit_drops_key(self):
        profile = _make_profile(headline=None)
        config = {"fields": [{"path": "headline", "type": "string"}], "on_missing": "omit"}
        out = project(profile, config)
        self.assertNotIn("headline", out)

    def test_on_missing_omit_keeps_present_fields(self):
        profile = _make_profile(headline=None)
        config = {"fields": [
            {"path": "full_name", "type": "string"},
            {"path": "headline",  "type": "string"},
        ], "on_missing": "omit"}
        out = project(profile, config)
        self.assertIn("full_name", out)
        self.assertNotIn("headline", out)


# ---------------------------------------------------------------------------
# project() — include_confidence / include_provenance
# ---------------------------------------------------------------------------

class TestProjectToggles(unittest.TestCase):
    def test_include_confidence_true(self):
        config = {"fields": [], "include_confidence": True, "on_missing": "null"}
        out = project(PROFILE, config)
        self.assertIn("overall_confidence", out)
        self.assertEqual(out["overall_confidence"], 0.9)

    def test_include_confidence_false(self):
        config = {"fields": [], "include_confidence": False, "on_missing": "null"}
        out = project(PROFILE, config)
        self.assertNotIn("overall_confidence", out)

    def test_include_provenance_true(self):
        config = {"fields": [], "include_provenance": True, "on_missing": "null"}
        out = project(PROFILE, config)
        self.assertIn("provenance", out)
        self.assertIsInstance(out["provenance"], list)

    def test_include_provenance_false(self):
        config = {"fields": [], "include_provenance": False, "on_missing": "null"}
        out = project(PROFILE, config)
        self.assertNotIn("provenance", out)


# ---------------------------------------------------------------------------
# project() — assignment example config
# ---------------------------------------------------------------------------

class TestProjectAssignmentConfig(unittest.TestCase):
    """Verify the exact config from the assignment README works."""

    CUSTOM_CONFIG = {
        "fields": [
            {"path": "full_name",     "type": "string",   "required": True},
            {"path": "primary_email", "from": "emails[0]","type": "string",   "required": True},
            {"path": "phone",         "from": "phones[0]","type": "string"},
            {"path": "skills",        "from": "skills[].name", "type": "string[]"},
        ],
        "include_confidence": True,
        "include_provenance": False,
        "on_missing": "null",
    }

    def test_output_has_renamed_primary_email(self):
        out = project(PROFILE, self.CUSTOM_CONFIG)
        self.assertIn("primary_email", out)
        self.assertNotIn("emails", out)

    def test_output_has_renamed_phone(self):
        out = project(PROFILE, self.CUSTOM_CONFIG)
        self.assertIn("phone", out)
        self.assertNotIn("phones", out)

    def test_skills_is_list_of_strings(self):
        out = project(PROFILE, self.CUSTOM_CONFIG)
        self.assertIsInstance(out["skills"], list)
        for s in out["skills"]:
            self.assertIsInstance(s, str)

    def test_provenance_excluded(self):
        out = project(PROFILE, self.CUSTOM_CONFIG)
        self.assertNotIn("provenance", out)

    def test_confidence_included(self):
        out = project(PROFILE, self.CUSTOM_CONFIG)
        self.assertIn("overall_confidence", out)

    def test_no_unexpected_fields(self):
        out = project(PROFILE, self.CUSTOM_CONFIG)
        allowed = {"full_name", "primary_email", "phone", "skills", "overall_confidence"}
        self.assertEqual(set(out.keys()), allowed)


if __name__ == "__main__":
    unittest.main()
