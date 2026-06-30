"""
Multi-Source Candidate Data Transformer

Typed data models for each pipeline stage:
  RawRecord        → output of extractors
  NormalizedRecord → output of normalizer
  CanonicalProfile → output of merger (final canonical record)
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage 1 — Extractor output
# ---------------------------------------------------------------------------

class RawRecord(BaseModel):
    """Raw key-value pairs as pulled directly from a source, before any
    normalization.  Errors/warnings collected during extraction are stored
    here so the pipeline can continue with the remaining sources."""

    source_id: str          # e.g. "recruiter_csv", "recruiter_notes"
    source_type: str        # "structured" | "unstructured"
    data: dict[str, Any]   # raw field → raw value (strings, lists, etc.)
    errors: list[str] = Field(default_factory=list)  # non-fatal warnings


# ---------------------------------------------------------------------------
# Stage 2 — Normalizer output
# ---------------------------------------------------------------------------

class NormalizedRecord(BaseModel):
    """Canonical field names with normalized values.
    Every field is Optional because any source may be missing data."""

    source_id: str

    full_name: Optional[str] = None
    emails: list[str] = Field(default_factory=list)          # lowercase
    phones: list[str] = Field(default_factory=list)          # E.164
    location: Optional[dict[str, Optional[str]]] = None      # {city, region, country}
    links: Optional[dict[str, Any]] = None                   # {linkedin, github, portfolio, other[]}
    headline: Optional[str] = None
    skills: list[str] = Field(default_factory=list)          # canonical lowercase names
    experience: list[dict[str, Any]] = Field(default_factory=list)  # [{company, title, start, end, summary}]
    education: list[dict[str, Any]] = Field(default_factory=list)   # [{institution, degree, field, end_year}]
    years_experience: Optional[float] = None


# ---------------------------------------------------------------------------
# Stage 3 — Merger output  (the final canonical profile)
# ---------------------------------------------------------------------------

class SkillEntry(BaseModel):
    """A single skill with confidence and source attribution."""
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)


class ProvenanceEntry(BaseModel):
    """Tracks where a field value came from and how it was derived."""
    field: str
    source: str    # source_id that provided the winning value
    method: str    # "direct", "normalized", "extracted_from_text", "merged"


class CanonicalProfile(BaseModel):
    """The final merged, normalized, fully attributed candidate record.

    This is the internal representation — a separate projection layer
    (projector.py) reshapes it into the requested output schema.
    """

    candidate_id: str
    full_name: Optional[str] = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    location: Optional[dict[str, Optional[str]]] = None
    links: Optional[dict[str, Any]] = None
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[SkillEntry] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
