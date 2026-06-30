"""Tests for src/validator.py — build_json_schema() and validate()."""

import unittest

from jsonschema import ValidationError

from src.validator import build_json_schema, validate


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

def _config(*field_specs, include_confidence=False, include_provenance=False, on_missing="null"):
    """Build a minimal runtime config dict."""
    return {
        "fields": list(field_specs),
        "include_confidence": include_confidence,
        "include_provenance": include_provenance,
        "on_missing": on_missing,
    }


def _field(path, type_=None, required=False, **extra):
    """Build a single field spec."""
    spec = {"path": path}
    if type_ is not None:
        spec["type"] = type_
    if required:
        spec["required"] = True
    spec.update(extra)
    return spec


# ---------------------------------------------------------------------------
# build_json_schema — unit tests
# ---------------------------------------------------------------------------

class TestBuildJsonSchema(unittest.TestCase):
    """Verify that build_json_schema() emits correct JSON Schema fragments."""

    def test_schema_is_object_type(self):
        schema = build_json_schema(_config())
        self.assertEqual(schema["type"], "object")

    def test_draft07_schema_key_present(self):
        schema = build_json_schema(_config())
        self.assertIn("$schema", schema)
        self.assertIn("draft-07", schema["$schema"])

    # -- Type mappings -------------------------------------------------------

    def test_string_type_allows_null(self):
        schema = build_json_schema(_config(_field("full_name", "string")))
        prop = schema["properties"]["full_name"]
        self.assertIn("string", prop["type"])
        self.assertIn("null",   prop["type"])

    def test_number_type_allows_null(self):
        schema = build_json_schema(_config(_field("years_experience", "number")))
        prop = schema["properties"]["years_experience"]
        self.assertIn("number", prop["type"])
        self.assertIn("null",   prop["type"])

    def test_boolean_type_allows_null(self):
        schema = build_json_schema(_config(_field("active", "boolean")))
        prop = schema["properties"]["active"]
        self.assertIn("boolean", prop["type"])
        self.assertIn("null",    prop["type"])

    def test_object_type_allows_null(self):
        schema = build_json_schema(_config(_field("location", "object")))
        prop = schema["properties"]["location"]
        self.assertIn("object", prop["type"])
        self.assertIn("null",   prop["type"])

    def test_string_array_type(self):
        schema = build_json_schema(_config(_field("emails", "string[]")))
        prop = schema["properties"]["emails"]
        self.assertIn("array", prop["type"])
        self.assertEqual(prop["items"]["type"], "string")

    def test_object_array_type(self):
        schema = build_json_schema(_config(_field("skills", "object[]")))
        prop = schema["properties"]["skills"]
        self.assertIn("array", prop["type"])
        self.assertEqual(prop["items"]["type"], "object")

    def test_unknown_type_emits_empty_schema(self):
        schema = build_json_schema(_config(_field("mystery", "widget")))
        prop = schema["properties"]["mystery"]
        self.assertEqual(prop, {})

    def test_missing_type_emits_empty_schema(self):
        schema = build_json_schema(_config(_field("mystery")))
        prop = schema["properties"]["mystery"]
        self.assertEqual(prop, {})

    # -- Required fields -----------------------------------------------------

    def test_required_field_in_required_list(self):
        schema = build_json_schema(_config(_field("full_name", "string", required=True)))
        self.assertIn("full_name", schema["required"])

    def test_non_required_field_not_in_required_list(self):
        schema = build_json_schema(_config(_field("headline", "string", required=False)))
        self.assertNotIn("headline", schema.get("required", []))

    def test_no_required_key_when_nothing_required(self):
        schema = build_json_schema(_config(_field("headline", "string")))
        self.assertNotIn("required", schema)

    # -- Confidence / provenance toggles ------------------------------------

    def test_include_confidence_adds_number_property(self):
        schema = build_json_schema(_config(include_confidence=True))
        self.assertIn("overall_confidence", schema["properties"])
        self.assertIn("number", schema["properties"]["overall_confidence"]["type"])

    def test_exclude_confidence_omits_property(self):
        schema = build_json_schema(_config(include_confidence=False))
        self.assertNotIn("overall_confidence", schema["properties"])

    def test_include_provenance_adds_array_property(self):
        schema = build_json_schema(_config(include_provenance=True))
        self.assertIn("provenance", schema["properties"])
        self.assertIn("array", schema["properties"]["provenance"]["type"])

    def test_exclude_provenance_omits_property(self):
        schema = build_json_schema(_config(include_provenance=False))
        self.assertNotIn("provenance", schema["properties"])


# ---------------------------------------------------------------------------
# validate — happy-path (valid outputs must pass without exception)
# ---------------------------------------------------------------------------

class TestValidateValid(unittest.TestCase):
    """Passing cases — validate() must return None and not raise."""

    def _assert_valid(self, output, config):
        try:
            result = validate(output, config)
            self.assertIsNone(result)
        except ValidationError as exc:
            self.fail(f"validate() raised ValidationError unexpectedly: {exc}")

    def test_full_canonical_output_passes(self):
        """A complete, correctly-typed output for the default config passes."""
        config = _config(
            _field("candidate_id",     "string",   required=True),
            _field("full_name",        "string",   required=True),
            _field("emails",           "string[]"),
            _field("phones",           "string[]"),
            _field("location",         "object"),
            _field("links",            "object"),
            _field("headline",         "string"),
            _field("years_experience", "number"),
            _field("skills",           "object[]"),
            _field("experience",       "object[]"),
            _field("education",        "object[]"),
            include_confidence=True,
            include_provenance=True,
        )
        output = {
            "candidate_id":     "cand-001",
            "full_name":        "Sakshi Singh",
            "emails":           ["sakshi@example.com"],
            "phones":           ["+919876543210"],
            "location":         {"city": "Jaipur", "region": "Rajasthan", "country": "IN"},
            "links":            {"linkedin": None, "github": None, "portfolio": None, "other": []},
            "headline":         "Software Engineer",
            "years_experience": 3.5,
            "skills":           [{"name": "python", "confidence": 1.0, "sources": ["csv"]}],
            "experience":       [{"company": "TechNova", "title": "Engineer"}],
            "education":        [{"institution": "RTU", "degree": "B.Tech"}],
            "overall_confidence": 0.9,
            "provenance":       [{"field": "full_name", "source": "csv", "method": "direct"}],
        }
        self._assert_valid(output, config)

    def test_null_values_for_optional_fields_pass(self):
        """Optional fields set to None (null) should not cause a violation."""
        config = _config(
            _field("full_name", "string"),
            _field("headline",  "string"),
        )
        output = {"full_name": "Alex", "headline": None}
        self._assert_valid(output, config)

    def test_empty_arrays_pass(self):
        config = _config(_field("emails", "string[]"), _field("skills", "object[]"))
        output = {"emails": [], "skills": []}
        self._assert_valid(output, config)

    def test_custom_config_subset_passes(self):
        """Assignment-example custom config with renamed / remapped fields."""
        config = _config(
            _field("full_name",     "string",   required=True),
            _field("primary_email", "string",   required=True),
            _field("phone",         "string"),
            _field("skills",        "string[]"),
            include_confidence=True,
        )
        output = {
            "full_name":        "Sakshi Singh",
            "primary_email":    "sakshi@example.com",
            "phone":            "+919876543210",
            "skills":           ["python", "javascript"],
            "overall_confidence": 0.85,
        }
        self._assert_valid(output, config)

    def test_omit_policy_output_with_missing_optional_passes(self):
        """When on_missing='omit', optional keys may be absent — that's valid."""
        config = _config(
            _field("full_name", "string", required=True),
            _field("headline",  "string"),
            on_missing="omit",
        )
        # headline was omitted by the projector
        output = {"full_name": "Sakshi"}
        self._assert_valid(output, config)

    def test_extra_keys_in_output_pass(self):
        """additionalProperties: true — extra keys must not trigger an error."""
        config = _config(_field("full_name", "string"))
        output = {"full_name": "Sakshi", "unexpected_field": 42}
        self._assert_valid(output, config)

    def test_no_fields_config_empty_output_passes(self):
        config = _config()
        self._assert_valid({}, config)

    def test_integer_value_satisfies_number_type(self):
        """JSON Schema 'number' includes integers."""
        config = _config(_field("years_experience", "number"))
        output = {"years_experience": 5}   # int, not float
        self._assert_valid(output, config)


# ---------------------------------------------------------------------------
# validate — invalid outputs (must raise ValidationError with clear messages)
# ---------------------------------------------------------------------------

class TestValidateInvalid(unittest.TestCase):
    """Failing cases — validate() must raise ValidationError."""

    def _assert_invalid(self, output, config, *, msg_contains=None):
        with self.assertRaises(ValidationError) as ctx:
            validate(output, config)
        if msg_contains:
            self.assertIn(msg_contains, str(ctx.exception))
        return ctx.exception

    # -- Type violations -----------------------------------------------------

    def test_string_field_given_integer_raises(self):
        """'full_name' must be a string; passing an int should raise."""
        config = _config(_field("full_name", "string"))
        output = {"full_name": 12345}
        exc = self._assert_invalid(output, config)
        self.assertIn("full_name", str(exc))

    def test_number_field_given_string_raises(self):
        """'years_experience' must be a number; passing a string should raise."""
        config = _config(_field("years_experience", "number"))
        output = {"years_experience": "three"}
        exc = self._assert_invalid(output, config)
        self.assertIn("years_experience", str(exc))

    def test_string_array_field_given_string_raises(self):
        """'emails' must be an array; passing a bare string should raise."""
        config = _config(_field("emails", "string[]"))
        output = {"emails": "not_an_array@example.com"}
        exc = self._assert_invalid(output, config)
        self.assertIn("emails", str(exc))

    def test_string_array_field_given_number_in_items_raises(self):
        """'emails' items must be strings; a number item should raise."""
        config = _config(_field("emails", "string[]"))
        output = {"emails": ["valid@example.com", 99]}
        exc = self._assert_invalid(output, config)
        self.assertIn("emails", str(exc))

    def test_object_field_given_list_raises(self):
        """'location' must be an object; passing a list should raise."""
        config = _config(_field("location", "object"))
        output = {"location": ["Jaipur", "IN"]}
        exc = self._assert_invalid(output, config)
        self.assertIn("location", str(exc))

    def test_object_array_field_given_string_raises(self):
        """'skills' must be an array; passing a plain string should raise."""
        config = _config(_field("skills", "object[]"))
        output = {"skills": "python"}
        exc = self._assert_invalid(output, config)
        self.assertIn("skills", str(exc))

    def test_boolean_field_given_string_raises(self):
        config = _config(_field("active", "boolean"))
        output = {"active": "yes"}
        exc = self._assert_invalid(output, config)
        self.assertIn("active", str(exc))

    # -- Required-field violations -------------------------------------------

    def test_missing_required_field_raises(self):
        """A required field whose key is entirely absent should raise."""
        config = _config(_field("full_name", "string", required=True))
        output = {}   # full_name key missing
        exc = self._assert_invalid(output, config)
        self.assertIn("full_name", str(exc))

    def test_second_required_field_missing_raises(self):
        """When multiple fields are required, any absent one triggers an error."""
        config = _config(
            _field("full_name",     "string", required=True),
            _field("candidate_id",  "string", required=True),
        )
        output = {"full_name": "Sakshi"}   # candidate_id missing
        exc = self._assert_invalid(output, config)
        self.assertIn("candidate_id", str(exc))

    # -- Error message quality -----------------------------------------------

    def test_error_message_contains_field_path(self):
        """The ValidationError message must identify the offending field."""
        config = _config(_field("years_experience", "number"))
        output = {"years_experience": "five"}
        exc = self._assert_invalid(output, config)
        # Must name the field
        self.assertIn("years_experience", str(exc))

    def test_error_message_contains_expected_schema(self):
        """The ValidationError message must echo the expected schema."""
        config = _config(_field("emails", "string[]"))
        output = {"emails": "not_a_list"}
        exc = self._assert_invalid(output, config)
        # Our enriched message always includes "Expected schema:"
        self.assertIn("Expected schema", str(exc))

    def test_error_message_contains_offending_value(self):
        """The ValidationError message must echo the offending value."""
        config = _config(_field("full_name", "string"))
        output = {"full_name": [1, 2, 3]}
        exc = self._assert_invalid(output, config)
        self.assertIn("Offending value", str(exc))


if __name__ == "__main__":
    unittest.main()
