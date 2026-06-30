"""Output configurator (projector) — transforms a CanonicalProfile into the
requested output shape using a runtime config dict.

Responsibilities (this module only):
  - resolve_path()   : read a value from the profile dict by path expression
  - handle_missing() : decide what to do when a value is None/missing
  - project()        : assemble the output dict from the config field list

Supported path formats:
  "full_name"        → profile["full_name"]
  "emails[0]"        → profile["emails"][0]
  "skills[].name"    → [s["name"] for s in profile["skills"]]

on_missing values:
  "null" → include the key with value null
  "omit" → exclude the key from output entirely

This module does NOT merge, normalize, validate, or make business decisions.
"""

from __future__ import annotations

import re
from typing import Any

from src.models import CanonicalProfile

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_RE_INDEX = re.compile(r'^(\w+)\[(\d+)\]$')   # emails[0]
_RE_MAP   = re.compile(r'^(\w+)\[\]\.(\w+)$') # skills[].name


def resolve_path(profile_dict: dict, path: str) -> Any:
    """Resolve a path expression against a flat profile dict.

    Three cases:
      1. Simple    "full_name"       → direct key lookup
      2. Index     "emails[0]"       → list access by integer index
      3. Map       "skills[].name"   → extract one field from every list item
    Returns None if the path cannot be resolved (missing key, out-of-range, etc.)
    """
    # Case 3: array map  e.g. "skills[].name"
    m = _RE_MAP.match(path)
    if m:
        key, field = m.group(1), m.group(2)
        items = profile_dict.get(key) or []
        if not isinstance(items, list):
            return None
        result = []
        for item in items:
            if isinstance(item, dict) and field in item:
                result.append(item[field])
        return result if result else None

    # Case 2: array index  e.g. "emails[0]"
    m = _RE_INDEX.match(path)
    if m:
        key, idx = m.group(1), int(m.group(2))
        items = profile_dict.get(key) or []
        if isinstance(items, list) and idx < len(items):
            return items[idx]
        return None

    # Case 1: simple key  e.g. "full_name"
    return profile_dict.get(path)


# ---------------------------------------------------------------------------
# Missing value handling
# ---------------------------------------------------------------------------

def handle_missing(on_missing: str) -> Any:
    """Return the sentinel for a missing value based on config policy.

    "null" → None  (key is included with null value)
    "omit" → _OMIT (caller must exclude the key from output)
    """
    if on_missing == "omit":
        return _OMIT
    return None   # default: "null"


_OMIT = object()  # sentinel — signals the key should be dropped from output


# ---------------------------------------------------------------------------
# Projector
# ---------------------------------------------------------------------------

def project(profile: CanonicalProfile, config: dict) -> dict:
    """Transform a CanonicalProfile into an output dict shaped by config.

    For each field spec in config["fields"]:
      - Resolve the value via resolve_path() using "from" if given else "path"
      - If value is None, apply handle_missing()
      - Write result under config["path"] (the output key name)

    Appends overall_confidence if config["include_confidence"] is true.
    Appends provenance     if config["include_provenance"]  is true.
    """
    profile_dict = profile.model_dump()
    on_missing   = config.get("on_missing", "null")
    output: dict = {}

    for field_spec in config.get("fields", []):
        out_key  = field_spec["path"]
        src_path = field_spec.get("from", out_key)

        value = resolve_path(profile_dict, src_path)

        if value is None:
            value = handle_missing(on_missing)
            if value is _OMIT:
                continue          # drop key entirely

        output[out_key] = value

    if config.get("include_confidence", False):
        output["overall_confidence"] = profile_dict.get("overall_confidence")

    if config.get("include_provenance", False):
        output["provenance"] = profile_dict.get("provenance", [])

    return output
