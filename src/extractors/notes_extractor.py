"""Notes extractor — parses free-text recruiter notes into RawRecords.

Strategy:
  1. Split the file into per-candidate blocks on '---' separator lines.
  2. For each block, apply regex patterns to extract fields.
  3. Wrap everything in try/except — no block failure propagates to others.

Design decisions:
  - Regex + keyword matching only; no NLP.
  - Skills are extracted as raw strings and left for normalizer.normalize_skill()
    to canonicalize — keeps extraction and normalization cleanly separated.
  - Experience / education parsed from '|'-delimited lines under section headers.
  - Dates are extracted as raw strings; normalizer.normalize_date() converts them.
  - Unknown/unparseable values are omitted rather than invented.
"""

from __future__ import annotations

import re
from src.extractors.base import BaseExtractor
from src.models import RawRecord

SOURCE_ID = "recruiter_notes"

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_RE_EMAIL   = re.compile(r'[\w.+-]+@[\w.-]+\.\w{2,}')
_RE_PHONE   = re.compile(r'(?:\+?\d[\d\s\-\(\)\.]{7,}\d)')
_RE_URL     = re.compile(r'https?://\S+')
_RE_NAME    = re.compile(r'Candidate:\s*(.+)', re.IGNORECASE)
_RE_LOC     = re.compile(r'Location:\s*(.+)', re.IGNORECASE)

# Matches "2022-06 to present" or "2021-01 to 2022-05"
_RE_DATE_RANGE = re.compile(
    r'(\d{4}-\d{2})\s+to\s+(\d{4}-\d{2}|present)', re.IGNORECASE
)

# Skill keywords to look for in free text (raw, normalizer will canonicalize)
_KNOWN_SKILLS = {
    "python", "javascript", "js", "typescript", "ts",
    "react", "react.js", "reactjs", "node", "node.js", "nodejs",
    "sql", "postgresql", "postgres", "mongodb", "mongo",
    "docker", "kubernetes", "k8s", "git",
    "aws", "gcp", "azure",
    "machine learning", "ml", "ai",
    "java", "spring boot",
    "excel", "tableau", "power bi",
    "rest apis", "rest api",
}


# ---------------------------------------------------------------------------
# Block-level helpers
# ---------------------------------------------------------------------------

def _extract_name(block: str) -> str | None:
    m = _RE_NAME.search(block)
    return m.group(1).strip() if m else None


def _extract_emails(block: str) -> list[str]:
    return list(dict.fromkeys(_RE_EMAIL.findall(block)))  # dedup, preserve order


def _extract_phones(block: str) -> list[str]:
    return list(dict.fromkeys(
        p.strip() for p in _RE_PHONE.findall(block) if len(re.sub(r'\D', '', p)) >= 10
    ))


def _extract_urls(block: str) -> dict:
    """Classify URLs by domain into linkedin / github / portfolio / other."""
    links: dict = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    for url in _RE_URL.findall(block):
        url = url.rstrip('.,)')
        low = url.lower()
        if "linkedin.com" in low and links["linkedin"] is None:
            links["linkedin"] = url
        elif "github.com" in low and links["github"] is None:
            links["github"] = url
        elif links["portfolio"] is None and "linkedin.com" not in low and "github.com" not in low:
            links["portfolio"] = url
        else:
            if url not in links["other"]:
                links["other"].append(url)
    return links


def _extract_skills(block: str) -> list[str]:
    """Extract skills from a 'Skills:' section or dash-list.

    First tries to find a dedicated Skills section; if found, parses it.
    Returns raw strings — normalizer.normalize_skill() handles canonicalization.
    """
    skills: list[str] = []

    # Try to find Skills section (handles both "Skills:" and "Skills mentioned...")
    section_match = re.search(
        r'Skills[^:\n]*:\s*\n?(.*?)(?=\n\n|\nLinkedIn|\nGitHub|\nExperience|\nEducation|\nLocation|\nNotes|---|\Z)',
        block, re.DOTALL | re.IGNORECASE
    )
    if section_match:
        section_text = section_match.group(1)
        # Dash-list format: "- Python, JavaScript, React"
        dash_items = re.findall(r'-\s*(.+)', section_text)
        if dash_items:
            for item in dash_items:
                for skill in re.split(r'[,;]', item):
                    skill = skill.strip()
                    if skill:
                        skills.append(skill)
        else:
            # Inline comma format: "Python, SQL, Tableau"
            for skill in re.split(r'[,;]', section_text):
                skill = skill.strip()
                if skill:
                    skills.append(skill)

    # Fallback: scan free text for known skill keywords
    if not skills:
        lower_block = block.lower()
        for kw in sorted(_KNOWN_SKILLS):
            if re.search(r'\b' + re.escape(kw) + r'\b', lower_block):
                skills.append(kw)

    return [s for s in skills if s]


def _extract_experience(block: str) -> list[dict]:
    """Parse pipe-delimited lines under 'Experience:' section.

    Expected format:  - Company | Title | 2022-06 to present
    """
    experience: list[dict] = []
    section_match = re.search(
        r'Experience:\s*\n(.*?)(?=\n\n(?:Education|Location|Notes|LinkedIn|GitHub|Skills)|---|\Z)',
        block, re.DOTALL | re.IGNORECASE
    )
    if not section_match:
        return experience

    for line in section_match.group(1).splitlines():
        line = line.strip().lstrip('-').strip()
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2:
            continue
        company = parts[0]
        title   = parts[1]
        start, end = None, None
        if len(parts) >= 3:
            dr = _RE_DATE_RANGE.search(parts[2])
            if dr:
                start = dr.group(1)
                end   = None if dr.group(2).lower() == "present" else dr.group(2)
        experience.append({
            "company": company,
            "title": title,
            "start": start,
            "end": end,
            "summary": None,
        })
    return experience


def _extract_education(block: str) -> list[dict]:
    """Parse pipe-delimited lines under 'Education:' section.

    Expected format:  - Degree Field | Institution | Year
    """
    education: list[dict] = []
    section_match = re.search(
        r'Education:\s*\n(.*?)(?=\n\n(?:Location|Notes|LinkedIn|GitHub|Experience)|---|\Z)',
        block, re.DOTALL | re.IGNORECASE
    )
    if not section_match:
        return education

    for line in section_match.group(1).splitlines():
        line = line.strip().lstrip('-').strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split('|')]
        degree_full  = parts[0] if len(parts) >= 1 else None
        institution  = parts[1] if len(parts) >= 2 else None
        end_year     = None
        if len(parts) >= 3:
            yr = re.search(r'\d{4}', parts[2])
            end_year = int(yr.group()) if yr else None

        # Split "B.Tech Computer Science" → degree="B.Tech", field="Computer Science"
        degree, field = None, None
        if degree_full:
            tokens = degree_full.split(None, 1)
            degree = tokens[0] if tokens else degree_full
            field  = tokens[1] if len(tokens) > 1 else None

        education.append({
            "institution": institution,
            "degree": degree,
            "field": field,
            "end_year": end_year,
        })
    return education


def _extract_location(block: str) -> str | None:
    m = _RE_LOC.search(block)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Block splitter
# ---------------------------------------------------------------------------

def _split_into_blocks(text: str) -> list[str]:
    """Split file on lines that are just dashes (--- or ---...).
    The very first block is the file header — skip it if it has no 'Candidate:' line."""
    raw_blocks = re.split(r'\n---+\n', text)
    candidate_blocks = []
    for block in raw_blocks:
        block = block.strip()
        if block and _RE_NAME.search(block):
            candidate_blocks.append(block)
    return candidate_blocks


# ---------------------------------------------------------------------------
# Public extractor
# ---------------------------------------------------------------------------

class NotesExtractor(BaseExtractor):
    """Parses a recruiter notes .txt file containing one or more candidate
    blocks separated by '---' lines."""

    def extract(self, file_path: str) -> list[RawRecord]:
        records: list[RawRecord] = []
        try:
            with open(file_path, encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            return [RawRecord(
                source_id=SOURCE_ID, source_type="unstructured",
                data={}, errors=[f"File not found: {file_path}"]
            )]
        except Exception as exc:
            return [RawRecord(
                source_id=SOURCE_ID, source_type="unstructured",
                data={}, errors=[f"Failed to read {file_path}: {exc}"]
            )]

        blocks = _split_into_blocks(text)
        if not blocks:
            return [RawRecord(
                source_id=SOURCE_ID, source_type="unstructured",
                data={}, errors=["No candidate blocks found in notes file"]
            )]

        for block in blocks:
            try:
                data = {
                    "full_name":  _extract_name(block),
                    "emails":     ";".join(_extract_emails(block)),
                    "phones":     ";".join(_extract_phones(block)),
                    "links":      _extract_urls(block),
                    "skills_list": _extract_skills(block),
                    "experience": _extract_experience(block),
                    "education":  _extract_education(block),
                    "location":   _extract_location(block),
                }
                records.append(RawRecord(
                    source_id=SOURCE_ID,
                    source_type="unstructured",
                    data={k: v for k, v in data.items() if v not in (None, "", [], {})},
                ))
            except Exception as exc:
                records.append(RawRecord(
                    source_id=SOURCE_ID, source_type="unstructured",
                    data={}, errors=[f"Failed to parse candidate block: {exc}"]
                ))

        return records
