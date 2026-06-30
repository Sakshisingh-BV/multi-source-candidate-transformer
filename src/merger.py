"""Merger — merges a list of NormalizedRecords (all for the same candidate)
into one CanonicalProfile.

Merge policies (simple, explainable, deterministic):

  Edge case 1 — Conflicting scalar values:
    Source-priority wins. recruiter_csv (priority 1) beats recruiter_notes
    (priority 2) for any scalar field where both have a value. The losing
    value is not discarded — it is visible in the input NormalizedRecord and
    traceable via provenance.

  Edge case 2 — Partial records completing each other:
    Scalar merge walks sources in priority order and takes the FIRST non-null.
    So if CSV has name+email but no links, and notes has links but no name,
    the final profile has all three fields populated from their respective
    sources.

  Edge case 3 — Missing or garbage source:
    A failed extraction produces a NormalizedRecord with all fields None/[].
    _has_useful_data() filters these out before merging. If ALL records are
    empty after filtering, merge() returns a minimal profile with
    overall_confidence = 0.0 rather than crashing.

  Edge case 4 — Skill synonyms:
    By the time skills reach the merger they are already canonicalized by
    normalizer.normalize_skill() ("JS" → "javascript", "ML" → "machine
    learning", etc.). The merger simply unions canonical names and counts
    how many sources mentioned each one, making synonym deduplication free.

  List fields    → union across all sources, deduplicated, sorted.
  Skills         → union by canonical name; confidence = sources / total.
  Experience     → union, dedup by (company, title) exact match.
  Education      → union, dedup by (institution, degree) exact match.
  Links          → dict merge; higher-priority source wins per key.
  Provenance     → one entry per populated field.
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

# Fields that count toward overall_confidence.
_KEY_FIELDS = [
    "full_name", "emails", "phones", "location",
    "headline", "skills", "experience", "education",
    "years_experience", "links",
]


# ---------------------------------------------------------------------------
# Helper: detect empty / failed records (Edge case 3)
# ---------------------------------------------------------------------------

def _has_useful_data(rec: NormalizedRecord) -> bool:
    """Return True if the record has at least one non-empty field.
    Records produced by a failed extractor have all None/[] — skip them."""
    return any([
        rec.full_name,
        rec.emails,
        rec.phones,
        rec.location,
        rec.headline,
        rec.skills,
        rec.experience,
        rec.education,
        rec.years_experience is not None,
        rec.links,
    ])


def _priority(rec: NormalizedRecord) -> int:
    return SOURCE_PRIORITY.get(rec.source_id, 99)


# ---------------------------------------------------------------------------
# Scalar merge — Edge case 1 (conflict) + Edge case 2 (partial completion)
# ---------------------------------------------------------------------------

def _merge_scalar(
    field: str,
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> Any:
    """Walk sources in priority order; return the first non-None value.

    Conflict resolution: highest-priority source wins (Edge case 1).
    Partial completion: if the winner source has None, the next source
    fills the gap (Edge case 2). The losing value remains visible in the
    NormalizedRecord for debugging but is not included in the final profile.
    """
    for rec in records:
        value = getattr(rec, field, None)
        if value is not None:
            provenance.append(
                ProvenanceEntry(field=field, source=rec.source_id, method="direct")
            )
            return value
    return None


# ---------------------------------------------------------------------------
# List merge — union + dedup + deterministic sort
# ---------------------------------------------------------------------------

def _merge_list(
    field: str,
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> list:
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
            ProvenanceEntry(
                field=field,
                source=",".join(sources_used),
                method="union_dedup",
            )
        )
    return sorted(result)


# ---------------------------------------------------------------------------
# Links merge
# ---------------------------------------------------------------------------

def _merge_links(
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> Optional[dict]:
    merged: dict[str, Any] = {
        "linkedin": None, "github": None, "portfolio": None, "other": []
    }
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
            ProvenanceEntry(field="links", source=",".join(sources_used), method="dict_merge")
        )
        return merged
    return None


# ---------------------------------------------------------------------------
# Skill merge — Edge case 4 (synonyms already canonical; just count sources)
# ---------------------------------------------------------------------------

def _merge_skills(
    records: list[NormalizedRecord],
    total_sources: int,
    provenance: list[ProvenanceEntry],
) -> list[SkillEntry]:
    """Union skills by canonical name (synonym dedup is free — normalizer
    already ran). confidence = sources_mentioning / total_sources."""
    skill_sources: dict[str, list[str]] = {}
    for rec in records:
        for skill in rec.skills:
            skill_sources.setdefault(skill, [])
            if rec.source_id not in skill_sources[skill]:
                skill_sources[skill].append(rec.source_id)

    entries = [
        SkillEntry(
            name=name,
            confidence=round(len(srcs) / total_sources, 2),
            sources=sorted(srcs),
        )
        for name, srcs in skill_sources.items()
    ]
    # Highest confidence first; alphabetical within the same confidence tier.
    entries.sort(key=lambda e: (-e.confidence, e.name))

    if entries:
        provenance.append(
            ProvenanceEntry(
                field="skills",
                source="all_sources",
                method="union_with_confidence",
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Experience merge — union + dedup by (company, title)
# ---------------------------------------------------------------------------

def _merge_experience(
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for rec in records:
        for entry in rec.experience:
            key = (
                (entry.get("company") or "").lower().strip(),
                (entry.get("title") or "").lower().strip(),
            )
            if key not in seen:
                seen[key] = entry
            # Duplicate from a lower-priority source → silently skip.
    result = sorted(seen.values(), key=lambda e: e.get("start") or "", reverse=True)
    if result:
        provenance.append(
            ProvenanceEntry(
                field="experience",
                source="all_sources",
                method="union_dedup_by_company_title",
            )
        )
    return result


# ---------------------------------------------------------------------------
# Education merge — union + dedup by (institution, degree)
# ---------------------------------------------------------------------------

def _merge_education(
    records: list[NormalizedRecord],
    provenance: list[ProvenanceEntry],
) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for rec in records:
        for entry in rec.education:
            key = (
                (entry.get("institution") or "").lower().strip(),
                (entry.get("degree") or "").lower().strip(),
            )
            if key not in seen:
                seen[key] = entry
    result = sorted(
        seen.values(),
        key=lambda e: str(e.get("end_year") or ""),
        reverse=True,
    )
    if result:
        provenance.append(
            ProvenanceEntry(
                field="education",
                source="all_sources",
                method="union_dedup_by_institution_degree",
            )
        )
    return result


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def _compute_confidence(profile_data: dict[str, Any]) -> float:
    """overall_confidence = proportion of key fields that are non-null/non-empty.
    Simple and explainable: a profile with all 10 key fields populated = 1.0."""
    filled = sum(
        1 for f in _KEY_FIELDS
        if profile_data.get(f) not in (None, [], {})
    )
    return round(filled / len(_KEY_FIELDS), 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge(records: list[NormalizedRecord]) -> CanonicalProfile:
    """Merge all NormalizedRecords for a single candidate into one
    CanonicalProfile.

    Graceful degradation (Edge case 3): records that contain no useful data
    (produced by failed extractions) are filtered out before merging. If
    nothing remains, returns a minimal empty profile with confidence = 0.0
    rather than raising.
    """
    if not records:
        raise ValueError("merge() requires at least one NormalizedRecord.")

    # Edge case 3: filter out empty / failed records.
    valid = [r for r in records if _has_useful_data(r)]
    if not valid:
        return CanonicalProfile(
            candidate_id=str(uuid.uuid4()),
            overall_confidence=0.0,
        )

    sorted_records = sorted(valid, key=_priority)
    total_sources = len(sorted_records)
    provenance: list[ProvenanceEntry] = []

    # Scalar fields (Edge cases 1 + 2)
    full_name = _merge_scalar("full_name", sorted_records, provenance)
    headline = _merge_scalar("headline", sorted_records, provenance)
    location = _merge_scalar("location", sorted_records, provenance)
    years_experience = _merge_scalar("years_experience", sorted_records, provenance)

    # List fields
    emails = _merge_list("emails", sorted_records, provenance)
    phones = _merge_list("phones", sorted_records, provenance)

    # Composite fields
    links = _merge_links(sorted_records, provenance)
    skills = _merge_skills(sorted_records, total_sources, provenance)  # Edge case 4
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
