"""Milestone 6 verification: Notes → RawRecord → NormalizedRecord → Merge with CSV → CanonicalProfile."""

import json
from src.extractors.csv_extractor import CsvExtractor
from src.extractors.notes_extractor import NotesExtractor
from src.normalizer import normalize
from src.merger import merge

DIVIDER = "-" * 60

# ── 1. Extract ────────────────────────────────────────────────
csv_raws   = CsvExtractor().extract("data/sample_candidates.csv")
notes_raws = NotesExtractor().extract("data/recruiter_notes.txt")

print(f"CSV records   : {len(csv_raws)}")
print(f"Notes records : {len(notes_raws)}")
print()

# ── 2. Show raw notes records ─────────────────────────────────
for i, raw in enumerate(notes_raws, 1):
    print(f"[RawRecord {i} — recruiter_notes]")
    print(json.dumps(raw.data, indent=2, default=str))
    print(DIVIDER)

# ── 3. Normalize all records ──────────────────────────────────
csv_normalized   = [normalize(r) for r in csv_raws]
notes_normalized = [normalize(r) for r in notes_raws]

print("\n[NormalizedRecord — Sakshi from notes]")
sakshi_notes_nr = notes_normalized[0]
print(f"  name     : {sakshi_notes_nr.full_name}")
print(f"  emails   : {sakshi_notes_nr.emails}")
print(f"  phones   : {sakshi_notes_nr.phones}")
print(f"  location : {sakshi_notes_nr.location}")
print(f"  skills   : {sakshi_notes_nr.skills}")
print(f"  exp      : {[e['company'] for e in sakshi_notes_nr.experience]}")
print(f"  edu      : {[e['institution'] for e in sakshi_notes_nr.education]}")
print(f"  years_exp: {sakshi_notes_nr.years_experience}")
print()

# ── 4. Merge Sakshi (CSV row 0 + Notes record 0) ─────────────
print("[CanonicalProfile — Sakshi Singh (CSV + Notes merged)]")
sakshi_profile = merge([csv_normalized[0], notes_normalized[0]])
print(json.dumps(sakshi_profile.model_dump(), indent=2, default=str))
print(DIVIDER)

# ── 5. Merge Rahul (CSV row 1 + Notes record 1) ──────────────
print("[CanonicalProfile — Rahul Sharma (CSV + Notes merged)]")
rahul_profile = merge([csv_normalized[1], notes_normalized[1]])
print(json.dumps(rahul_profile.model_dump(), indent=2, default=str))
