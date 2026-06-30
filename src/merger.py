"""Merger — merges a list of NormalizedRecords (all for the same candidate)
into one CanonicalProfile.

Merge policies:
  Scalar fields  → highest-priority non-null source wins.
  List fields    → union across all sources, deduplicated, deterministically sorted.
  Skills         → union by canonical name; confidence = sources_mentioning / total_sources.
  Experience     → union, deduplicated by (company, title) exact match.
  Education      → union, deduplicated by (institution, degree) exact match.
  Links          → dict merge; higher-priority source wins per key.
  Provenance     → one entry per field recording winning source + method.
  overall_confidence → proportion of key fields that are non-null/non-empty.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from src.models import CanonicalProfile, NormalizedRecord, ProvenanceEntry, SkillEntry

# Lower number = higher priority (structured sources trump unstructured).
SOURCE_PRIORITY: dict[str, int] = {
    "recruiter_csv": 1,
    "recruiter_notes": 2,
}

# Fields counted when computing overall_confidence.
_KEY_FIELDS = [
    "full_name", "emails", "phones", "location",
    "headline", "skills", "experience", "education",
    "years_experience", "links",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _priority(record: NormalizedRecord) -> int:
    return SOURCE_PRIORITY.get(record.source_id, 99)


def _merge_scalar(
    field: str,
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> Any:
    """Return the first non-None value from the highest-priority source."""
    for rec in records:
        value = getattr(rec, field, None)
        if value is not None:
            provenance.append(ProvenanceEntry(field=field, source=rec.source_id, method="direct"))
            return value
    return None


def _merge_list(
    field: str,
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> list:
    """Union across all sources; deduplicated and sorted for determinism."""
    seen: set = set()
    result: list = []
    sources_used: list[str] = []
    for rec in records:
        items: list = getattr(rec, field, []) or []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
                if rec.source_id not in sources_used:
                    sources_used.append(rec.source_id)
    if result:
        provenance.append(
            ProvenanceEntry(field=field, source=",".join(sources_used), method="merged")
        )
    return sorted(result)


def _merge_links(
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> Optional[dict]:
    """Merge link dicts; highest-priority source wins per key."""
    merged: dict[str, Any] = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    sources_used: list[str] = []
    for rec in records:
        links = rec.links or {}
        for key in ("linkedin", "github", "portfolio"):
            if merged[key] is None and links.get(key):
                merged[key] = links[key]
                if rec.source_id not in sources_used:
                    sources_used.append(rec.source_id)
        for url in links.get("other", []):
            if url not in merged["other"]:
                merged["other"].append(url)

    has_any = any(merged[k] for k in ("linkedin", "github", "portfolio")) or merged["other"]
    if has_any:
        provenance.append(
            ProvenanceEntry(field="links", source=",".join(sources_used), method="merged")
        )
        return merged
    return None


def _merge_skills(
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> list[SkillEntry]:
    """Union skills by canonical name; confidence = sources_mentioning / total_sources."""
    total = len(records)
    skill_sources: dict[str, list[str]] = {}
    for rec in records:
        for skill in rec.skills:
            skill_sources.setdefault(skill, [])
            if rec.source_id not in skill_sources[skill]:
                skill_sources[skill].append(rec.source_id)

    entries = [
        SkillEntry(
            name=name,
            confidence=round(len(srcs) / total, 2),
            sources=sorted(srcs),
        )
        for name, srcs in skill_sources.items()
    ]
    entries.sort(key=lambda e: (-e.confidence, e.name))

    if entries:
        provenance.append(
            ProvenanceEntry(field="skills", source="all_sources", method="union_with_confidence")
        )
    return entries


def _merge_experience(
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> list[dict]:
    """Union experience entries; deduplicate by (company, title) exact match.
    When duplicate found, higher-priority source entry wins."""
    seen: dict[tuple, dict] = {}
    for rec in records:
        for entry in rec.experience:
            key = (
                (entry.get("company") or "").lower().strip(),
                (entry.get("title") or "").lower().strip(),
            )
            if key not in seen:
                seen[key] = entry
            # else: already have this entry from a higher-priority source; skip

    result = sorted(seen.values(), key=lambda e: e.get("start") or "", reverse=True)
    if result:
        provenance.append(
            ProvenanceEntry(field="experience", source="all_sources", method="union_dedup_by_company_title")
        )
    return result


def _merge_education(
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> list[dict]:
    """Union education entries; deduplicate by (institution, degree) exact match."""
    seen: dict[tuple, dict] = {}
    for rec in records:
        for entry in rec.education:
            key = (
                (entry.get("institution") or "").lower().strip(),
                (entry.get("degree") or "").lower().strip(),
            )
            if key not in seen:
                seen[key] = entry

    result = sorted(seen.values(), key=lambda e: str(e.get("end_year") or ""), reverse=True)
    if result:
        provenance.append(
            ProvenanceEntry(field="education", source="all_sources", method="union_dedup_by_institution_degree")
        )
    return result


def _compute_confidence(profile_data: dict[str, Any]) -> float:
    """Overall confidence = proportion of key fields that are non-null/non-empty."""
    filled = 0
    for field in _KEY_FIELDS:
        value = profile_data.get(field)
        if value is not None and value != [] and value != {}:
            filled += 1
    return round(filled / len(_KEY_FIELDS), 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge(records: list[NormalizedRecord]) -> CanonicalProfile:
    """Merge all NormalizedRecords (same candidate, multiple sources) into one
    CanonicalProfile.  Records are sorted by source priority before merging so
    scalar resolution is deterministic regardless of input order."""

    if not records:
        raise ValueError("merge() requires at least one NormalizedRecord")

    sorted_records = sorted(records, key=_priority)
    provenance: list[ProvenanceEntry] = []

    # Scalar fields
    full_name = _merge_scalar("full_name", sorted_records, provenance)
    headline = _merge_scalar("headline", sorted_records, provenance)
    location = _merge_scalar("location", sorted_records, provenance)
    years_experience = _merge_scalar("years_experience", sorted_records, provenance)

    # List fields
    emails = _merge_list("emails", sorted_records, provenance)
    phones = _merge_list("phones", sorted_records, provenance)

    # Composite fields
    links = _merge_links(sorted_records, provenance)
    skills = _merge_skills(records, provenance)
    experience = _merge_experience(sorted_records, provenance)
    education = _merge_education(sorted_records, provenance)

    profile_data = {
        "full_name": full_name,
        "emails": emails,
        "phones": phones,
        "location": location,
        "headline": headline,
        "skills": skills,
        "experience": experience,
        "education": education,
        "years_experience": years_experience,
        "links": links,
    }

    return CanonicalProfile(
        candidate_id=str(uuid.uuid4()),
        provenance=provenance,
        overall_confidence=_compute_confidence(profile_data),
        **profile_data,
    )
