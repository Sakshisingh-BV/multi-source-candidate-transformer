"""
Multi-Source Candidate Data Transformer

validator.py — Validates a projected output dict against a JSON Schema that is
dynamically generated from the runtime output configuration.

Public API
----------
build_json_schema(config)  → dict          JSON Schema object
validate(output, config)   → None          Raises ValidationError on violation

Design notes
------------
- We use the ``jsonschema`` library; no custom schema engine.
- Type mapping (config → JSON Schema):
    "string"    → {"type": ["string", "null"]}
    "string[]"  → {"type": ["array", "null"], items: {"type": "string"}}
    "number"    → {"type": ["number", "null"]}
    "boolean"   → {"type": ["boolean", "null"]}
    "object"    → {"type": ["object", "null"]}
    "object[]"  → {"type": ["array", "null"], items: {"type": "object"}}
    (unknown)   → {}            (no constraint — accepts anything)
- Required fields (``"required": true`` in the config field spec) are collected
  and set on the schema's ``required`` list.  A null/None value for a required
  field will still pass JSON Schema type checking (null is allowed by default)
  but the field *key* must be present.
- The validator raises ``jsonschema.ValidationError`` so callers can catch it
  by the standard exception type.  The message is augmented to be human-readable.
"""

from __future__ import annotations

from typing import Any

import jsonschema
from jsonschema import ValidationError  # re-exported for callers  # noqa: F401


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, dict] = {
    "string":   {"type": ["string",  "null"]},
    "string[]": {"type": ["array",   "null"], "items": {"type": "string"}},
    "number":   {"type": ["number",  "null"]},
    "boolean":  {"type": ["boolean", "null"]},
    "object":   {"type": ["object",  "null"]},
    "object[]": {"type": ["array",   "null"], "items": {"type": "object"}},
}


def _field_schema(field_type: str | None) -> dict:
    """Return the JSON Schema fragment for a single field type string.

    Falls back to an empty schema (``{}``) for unrecognised or absent types,
    which means *no constraint* — anything is accepted.
    """
    if not field_type:
        return {}
    return dict(_TYPE_MAP.get(field_type, {}))  # shallow copy, safe for immutable values


# ---------------------------------------------------------------------------
# Schema builder
# ---------------------------------------------------------------------------

def build_json_schema(config: dict) -> dict:
    """Dynamically generate a JSON Schema from a runtime output configuration.

    Parameters
    ----------
    config:
        The runtime config dict (same shape as the JSON files in ``config/``).
        Expected keys:
          - ``fields``: list of field specs, each with at minimum ``path`` and
            optionally ``type`` and ``required``.
          - ``include_confidence``: bool — if True, ``overall_confidence`` is
            added as a ``number`` property.
          - ``include_provenance``: bool — if True, ``provenance`` is added as
            an ``array`` property.

    Returns
    -------
    dict
        A valid JSON Schema (draft-07) ``object`` schema.
    """
    properties: dict[str, Any] = {}
    required_fields: list[str] = []

    for field_spec in config.get("fields", []):
        path: str = field_spec["path"]
        field_type: str | None = field_spec.get("type")
        is_required: bool = bool(field_spec.get("required", False))

        properties[path] = _field_schema(field_type)

        if is_required:
            required_fields.append(path)

    # Confidence and provenance are always numeric / array when toggled on.
    if config.get("include_confidence", False):
        properties["overall_confidence"] = {"type": ["number", "null"]}

    if config.get("include_provenance", False):
        properties["provenance"] = {"type": ["array", "null"]}

    schema: dict[str, Any] = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": properties,
        "additionalProperties": True,  # tolerate extra fields silently
    }

    if required_fields:
        schema["required"] = required_fields

    return schema


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate(output: dict, config: dict) -> None:
    """Validate a projected output dict against the schema derived from *config*.

    Parameters
    ----------
    output:
        The dict returned by ``output_configurator.project()``.
    config:
        The same runtime config that was used to produce *output*.

    Raises
    ------
    jsonschema.ValidationError
        When the output violates the generated schema.  The exception message
        is human-readable and pinpoints which field failed and why.

    Notes
    -----
    - Missing / null values are **not** treated as schema violations unless the
      field is marked ``"required": true`` **and** the key is entirely absent
      from the output dict.
    - Type mismatches (e.g. a string where a number is expected) are always
      reported.
    """
    schema = build_json_schema(config)

    try:
        jsonschema.validate(instance=output, schema=schema)
    except ValidationError as exc:
        # Enrich the message with a human-readable path indicator.
        field_path = " → ".join(str(p) for p in exc.absolute_path) or "<root>"
        human_msg = (
            f"Output validation failed at '{field_path}': {exc.message}.\n"
            f"  Expected schema: {exc.schema}\n"
            f"  Offending value: {exc.instance!r}"
        )
        raise ValidationError(human_msg) from exc
