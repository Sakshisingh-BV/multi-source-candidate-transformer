"""Normalizer — converts a RawRecord into a NormalizedRecord.

Each normalize_*() helper is pure and independently testable.
The main normalize() function maps raw field names → canonical names
and applies all normalizations.
"""

from __future__ import annotations

import re
from typing import Optional

import phonenumbers
from dateutil import parser as dateutil_parser

from src.models import NormalizedRecord, RawRecord

# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

SKILL_SYNONYMS: dict[str, str] = {
    "py": "python", "python": "python",
    "js": "javascript", "javascript": "javascript",
    "ts": "typescript", "typescript": "typescript",
    "react.js": "react", "reactjs": "react", "react": "react",
    "node.js": "nodejs", "node": "nodejs", "nodejs": "nodejs",
    "ml": "machine learning", "machine learning": "machine learning",
    "ai": "artificial intelligence", "artificial intelligence": "artificial intelligence",
    "sql": "sql",
    "postgres": "postgresql", "postgresql": "postgresql",
    "mongo": "mongodb", "mongodb": "mongodb",
    "k8s": "kubernetes", "kubernetes": "kubernetes",
    "aws": "aws", "gcp": "gcp", "azure": "azure",
    "docker": "docker", "git": "git",
    "rest apis": "rest apis", "rest api": "rest apis",
    "spring boot": "spring boot", "java": "java",
    "excel": "excel", "tableau": "tableau", "power bi": "power bi",
}

COUNTRY_MAP: dict[str, str] = {
    "india": "IN", "in": "IN",
    "usa": "US", "united states": "US", "us": "US", "america": "US",
    "uk": "GB", "united kingdom": "GB", "england": "GB",
    "germany": "DE", "de": "DE",
    "canada": "CA", "ca": "CA",
    "australia": "AU", "au": "AU",
    "singapore": "SG", "sg": "SG",
    "uae": "AE", "dubai": "AE",
}

# Default country dial code → ISO for phone fallback
_DEFAULT_REGION = "IN"

# ---------------------------------------------------------------------------
# Individual normalizers
# ---------------------------------------------------------------------------

def normalize_phone(raw: str) -> Optional[str]:
    """Parse any phone string → E.164. Returns None if unparseable."""
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw, _DEFAULT_REGION)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def normalize_email(raw: str) -> Optional[str]:
    """Lowercase, strip whitespace, basic format check."""
    if not raw or not raw.strip():
        return None
    email = raw.strip().lower()
    if re.match(r"^[\w.+-]+@[\w.-]+\.\w{2,}$", email):
        return email
    return None


def normalize_date(raw: str) -> Optional[str]:
    """Parse any date string → YYYY-MM. Returns None if unparseable."""
    if not raw or not raw.strip():
        return None
    try:
        dt = dateutil_parser.parse(raw, default=dateutil_parser.parse("2000-01-01"))
        return dt.strftime("%Y-%m")
    except (ValueError, OverflowError):
        return None


def normalize_country(raw: str) -> Optional[str]:
    """Map country name / abbreviation → ISO-3166 alpha-2."""
    if not raw or not raw.strip():
        return None
    return COUNTRY_MAP.get(raw.strip().lower())


def normalize_skill(raw: str) -> str:
    """Lowercase + synonym map → canonical skill name."""
    return SKILL_SYNONYMS.get(raw.strip().lower(), raw.strip().lower())


# ---------------------------------------------------------------------------
# Location parser
# ---------------------------------------------------------------------------

def _parse_location(raw: str) -> Optional[dict[str, Optional[str]]]:
    """Best-effort: 'Jaipur, Rajasthan, India' → {city, region, country}."""
    if not raw or not raw.strip():
        return None
    parts = [p.strip() for p in raw.split(",")]
    city = parts[0] if len(parts) >= 1 else None
    region = parts[1] if len(parts) >= 2 else None
    country_raw = parts[-1] if len(parts) >= 2 else parts[0]
    country = normalize_country(country_raw)
    return {"city": city, "region": region if len(parts) >= 3 else None, "country": country}


# ---------------------------------------------------------------------------
# Link classifier
# ---------------------------------------------------------------------------

def _classify_links(urls: list[str]) -> dict:
    links: dict = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    for url in urls:
        u = url.lower()
        if "linkedin.com" in u:
            links["linkedin"] = url
        elif "github.com" in u:
            links["github"] = url
        else:
            links["other"].append(url)
    return links


# ---------------------------------------------------------------------------
# Skills list parser (handles "Python;SQL;Git" or "Python, SQL, Git")
# ---------------------------------------------------------------------------

def _parse_skills(raw: str) -> list[str]:
    if not raw:
        return []
    sep = ";" if ";" in raw else ","
    return [normalize_skill(s) for s in raw.split(sep) if s.strip()]


# ---------------------------------------------------------------------------
# Main normalize function
# ---------------------------------------------------------------------------

def normalize(raw: RawRecord) -> NormalizedRecord:
    """Map a RawRecord's fields → NormalizedRecord with canonical values.

    Field mapping handles both CSV column names and notes-extractor keys.
    Unknown / missing fields silently become None / [].
    """
    d = raw.data

    # --- name ---
    full_name = d.get("full_name") or d.get("name") or None
    if full_name:
        full_name = full_name.strip()

    # --- emails ---
    emails: list[str] = []
    for key in ("email", "emails"):
        val = d.get(key)
        if val:
            for e in re.split(r"[;,\s]+", val):
                norm = normalize_email(e)
                if norm and norm not in emails:
                    emails.append(norm)

    # --- phones ---
    phones: list[str] = []
    for key in ("phone", "phones"):
        val = d.get(key)
        if val:
            for p in re.split(r"[;,]+", val):
                norm = normalize_phone(p.strip())
                if norm and norm not in phones:
                    phones.append(norm)

    # --- location ---
    location = _parse_location(d.get("location") or "")

    # --- links ---
    # Notes extractor stores a pre-classified dict under data["links"].
    # CSV records may store individual keys or a "urls" list.
    if isinstance(d.get("links"), dict):
        links = d["links"]
    else:
        raw_urls: list[str] = d.get("urls", []) if isinstance(d.get("urls"), list) else []
        links = _classify_links(raw_urls) if raw_urls else None
        if d.get("linkedin"):
            links = links or {"linkedin": None, "github": None, "portfolio": None, "other": []}
            links["linkedin"] = d["linkedin"]
        if d.get("github"):
            links = links or {"linkedin": None, "github": None, "portfolio": None, "other": []}
            links["github"] = d["github"]
        if d.get("portfolio"):
            links = links or {"linkedin": None, "github": None, "portfolio": None, "other": []}
            links["portfolio"] = d["portfolio"]

    # --- headline ---
    headline = d.get("headline") or d.get("title") or None
    if headline:
        headline = headline.strip()

    # --- skills ---
    skills: list[str] = []
    if d.get("skills"):
        skills = _parse_skills(d["skills"])
    # notes extractor may produce a list directly
    if d.get("skills_list") and isinstance(d["skills_list"], list):
        for s in d["skills_list"]:
            canon = normalize_skill(s)
            if canon not in skills:
                skills.append(canon)

    # --- experience ---
    experience: list[dict] = d.get("experience", []) if isinstance(d.get("experience"), list) else []
    # Normalize dates inside experience entries
    normalized_exp = []
    for entry in experience:
        normalized_exp.append({
            "company": entry.get("company"),
            "title": entry.get("title"),
            "start": normalize_date(entry.get("start", "")) if entry.get("start") else None,
            "end": normalize_date(entry.get("end", "")) if entry.get("end") else None,
            "summary": entry.get("summary"),
        })

    # --- education ---
    education: list[dict] = d.get("education", []) if isinstance(d.get("education"), list) else []

    # --- years_experience ---
    years_experience: Optional[float] = None
    if d.get("years_experience") is not None:
        try:
            years_experience = float(d["years_experience"])
        except (ValueError, TypeError):
            pass
    elif normalized_exp:
        # Compute from experience date ranges
        from datetime import date
        total_months = 0
        for entry in normalized_exp:
            try:
                s = dateutil_parser.parse(entry["start"]) if entry.get("start") else None
                e = dateutil_parser.parse(entry["end"]) if entry.get("end") else date.today()
                if s:
                    delta = (e.year - s.year) * 12 + (e.month - s.month)
                    total_months += max(0, delta)
            except Exception:
                pass
        if total_months:
            years_experience = round(total_months / 12, 1)

    return NormalizedRecord(
        source_id=raw.source_id,
        full_name=full_name,
        emails=emails,
        phones=phones,
        location=location,
        links=links,
        headline=headline,
        skills=skills,
        experience=normalized_exp,
        education=education,
        years_experience=years_experience,
    )
