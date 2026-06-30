"""
pipeline.py — Thin orchestration helper used by main.py.

Responsibilities (only):
  1. Detect the right extractor for each source file by extension.
  2. Run extract → normalize per source file.
  3. Group NormalizedRecords by candidate name (case-insensitive).
  4. Run merge → project → validate per candidate group.
  5. Return a list of (output_dict, warnings) tuples — one per candidate.

No business logic lives here; every step delegates to the relevant module.
"""

from __future__ import annotations

import os
from typing import Any

from src.extractors.csv_extractor import CsvExtractor
from src.extractors.notes_extractor import NotesExtractor
from src.models import NormalizedRecord
from src.normalizer import normalize
from src.merger import merge
from src.output_configurator import project
from src.validator import validate

# ---------------------------------------------------------------------------
# Extractor registry — map file extension → extractor class
# ---------------------------------------------------------------------------

_EXTRACTOR_MAP: dict[str, type] = {
    ".csv": CsvExtractor,
    ".txt": NotesExtractor,
}


def _extractor_for(file_path: str):
    """Return an instantiated extractor for the given file path.

    Raises ValueError for unrecognised extensions so main.py can surface
    a clean error without a traceback.
    """
    ext = os.path.splitext(file_path)[1].lower()
    cls = _EXTRACTOR_MAP.get(ext)
    if cls is None:
        supported = ", ".join(_EXTRACTOR_MAP.keys())
        raise ValueError(
            f"Unsupported source file extension '{ext}' for '{file_path}'. "
            f"Supported: {supported}"
        )
    return cls()


# ---------------------------------------------------------------------------
# Candidate grouping — by normalised full_name
# ---------------------------------------------------------------------------

def _group_by_candidate(
    records: list[NormalizedRecord],
) -> dict[str, list[NormalizedRecord]]:
    """Group NormalizedRecords by candidate name (lowercased, stripped).

    Records with no name are collected under the sentinel key '_unknown_'.
    This keeps the merge step per-candidate without silently dropping anyone.
    """
    groups: dict[str, list[NormalizedRecord]] = {}
    for rec in records:
        key = (rec.full_name or "").strip().lower() or "_unknown_"
        groups.setdefault(key, []).append(rec)
    return groups


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    source_paths: list[str],
    config: dict[str, Any],
) -> list[tuple[dict, list[str]]]:
    """Run the full pipeline for a list of source files and a runtime config.

    Parameters
    ----------
    source_paths:
        Absolute or relative paths to the source files to process.
    config:
        The runtime output configuration dict (loaded from JSON by main.py).

    Returns
    -------
    list of (output_dict, warnings)
        One tuple per candidate.  *output_dict* is the projected, validated
        output ready to serialise.  *warnings* is a list of non-fatal
        messages collected during extraction (e.g. a partial parse).

    Raises
    ------
    ValueError
        For unrecognised file extensions.  All other errors are caught and
        surfaced as warnings so the pipeline never crashes mid-run.
    """
    # ── Step 1: Extract + Normalize ──────────────────────────────────────────
    all_normalized: list[NormalizedRecord] = []
    all_warnings: list[str] = []

    for path in source_paths:
        extractor = _extractor_for(path)   # may raise ValueError — propagate up
        raw_records = extractor.extract(path)

        for raw in raw_records:
            # Surface any extraction warnings but keep going.
            all_warnings.extend(raw.errors)
            normalized = normalize(raw)
            all_normalized.append(normalized)

    if not all_normalized:
        return []

    # ── Step 2: Group by candidate ────────────────────────────────────────────
    groups = _group_by_candidate(all_normalized)

    # ── Step 3: Merge → Project → Validate per candidate group ───────────────
    results: list[tuple[dict, list[str]]] = []

    for name_key, records in groups.items():
        candidate_warnings = list(all_warnings)  # carry global warnings per candidate

        # Merge
        profile = merge(records)

        # Project (output configurator)
        output = project(profile, config)

        # Validate — non-fatal: report error but still include the output
        try:
            validate(output, config)
        except Exception as exc:
            candidate_warnings.append(f"Validation warning for '{name_key}': {exc}")

        results.append((output, candidate_warnings))

    return results
