"""Milestone 5 verification: CSV → Normalize → + synthetic notes NormalizedRecord → Merge → print CanonicalProfile."""

import json
from src.extractors.csv_extractor import CsvExtractor
from src.normalizer import normalize
from src.models import NormalizedRecord
from src.merger import merge

# --- Source 1: CSV extractor (structured) ---
csv_records = CsvExtractor().extract("data/sample_candidates.csv")
# Use first candidate (Sakshi Singh)
csv_normalized = normalize(csv_records[0])

# --- Source 2: Simulate what notes extractor will produce for Sakshi ---
# (Notes extractor is Milestone 6; using manual NormalizedRecord here to demo merge)
notes_normalized = NormalizedRecord(
    source_id="recruiter_notes",
    full_name="Sakshi S.",                        # conflict: CSV wins
    emails=["sakshi.s@gmail.com"],               # extra email
    phones=["+919876543210"],                    # same phone
    location={"city": "Jaipur", "region": "Rajasthan", "country": "IN"},
    links={
        "linkedin": "https://linkedin.com/in/sakshisingh",
        "github": "https://github.com/sakshisingh",
        "portfolio": None,
        "other": [],
    },
    headline="Senior Software Developer",        # conflict: CSV wins
    skills=["python", "javascript", "react", "sql", "rest apis", "docker"],  # superset
    experience=[
        {"company": "TechNova Solutions", "title": "Senior Software Developer", "start": "2022-06", "end": None, "summary": None},
        {"company": "WebStart Labs", "title": "Junior Developer", "start": "2021-01", "end": "2022-05", "summary": None},
    ],
    education=[
        {"institution": "Rajasthan Technical University", "degree": "B.Tech", "field": "Computer Science", "end_year": 2021}
    ],
    years_experience=3.0,
)

# --- Merge ---
profile = merge([csv_normalized, notes_normalized])

# --- Print ---
print(json.dumps(profile.model_dump(), indent=2))
