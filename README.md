# Multi-Source Candidate Data Transformer

## Project Overview

Hiring platforms receive candidate data from multiple sources — structured exports, free-text notes, and more. Each source uses different field names and formats, and the same candidate may appear across sources with conflicting values.

This project builds a Python pipeline that ingests data from multiple sources, normalizes it, merges conflicting records into one canonical profile per candidate, and outputs schema-validated JSON. Every field is traceable to its source, and a runtime configuration reshapes the output without code changes.

---

## Assignment Coverage

- **Structured source**: Recruiter CSV
- **Unstructured source**: Recruiter Notes (.txt)
- **Data normalization**: Phones (E.164), dates (YYYY-MM), countries (ISO-3166), skills (canonical synonyms)
- **Canonical profile generation**: Single merged profile per candidate
- **Conflict resolution**: Source-priority-based deterministic merge
- **Provenance tracking**: Every field records its source and merge method
- **Confidence scoring**: Per-skill and overall profile confidence
- **Runtime configurable output**: Field selection, renaming, and metadata toggles via JSON config
- **Output validation**: Dynamic JSON Schema generation and validation
- **Graceful degradation**: Individual source failures do not crash the pipeline

---

## Project Structure

```
├── config/          # Runtime output configuration files
├── data/            # Sample input source files
├── docs/            # Design document (one-page technical design)
├── output/          # Generated output JSON files
├── src/             # Core pipeline modules (extractors, normalizer, merger, configurator, validator)
├── tests/           # Unit tests for all pipeline modules
├── main.py          # CLI entry point
└── requirements.txt # Python dependencies
```

---

## Requirements

- Python 3.10+
- Dependencies: `phonenumbers`, `python-dateutil`, `pydantic>=2.0`, `jsonschema>=4.0`, `pytest`

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Sakshisingh-BV/multi-source-candidate-transformer.git
cd multi-source-candidate-transformer

# Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Running the Project

### Generate Default Output (full canonical schema)

```bash
python main.py --sources data/sample_candidates.csv data/recruiter_notes.txt --output output/default_output.json
```

Produces `output/default_output.json` — complete canonical profiles for all candidates with all fields, provenance, and confidence included.

### Generate Custom Output (assignment example config)

```bash
python main.py --sources data/sample_candidates.csv data/recruiter_notes.txt --config config/custom_config.json --output output/custom_output.json
```

Produces `output/custom_output.json` — a projected subset with renamed fields (`primary_email` from `emails[0]`, `phone` from `phones[0]`, flat `skills` list), confidence included, provenance excluded.

### CLI Arguments

| Argument | Required | Description |
|---|---|---|
| `--sources` | Yes | One or more source files (.csv or .txt) |
| `--config` | No | Runtime config JSON (default: `config/default_config.json`) |
| `--output` | Yes | Path to write the resulting JSON array |

---

## Produced Outputs

### `output/default_output.json`
- Complete canonical profile per candidate (all 13 fields)
- Provenance array included (field, source, method)
- Overall confidence score included
- 3 candidates generated from the sample data

### `output/custom_output.json`
- Runtime-projected output using `config/custom_config.json`
- Renamed fields: `primary_email`, `phone`, flat `skills` list
- Subset of canonical profile (4 fields + confidence)
- Provenance excluded
- 3 candidates generated from the same data

---

## Walkthrough Example

**Input — Sakshi Singh appears in both sources with conflicting data:**

**CSV row:**
```
Sakshi Singh, sakshi.singh@email.com, +919876543210, TechNova Solutions, Software Engineer, "Python;SQL;Git;Docker"
```

**Notes block:**
```
Candidate: Sakshi Singh
Email: sakshi.s@gmail.com
Skills: Python, JavaScript, React, SQL, REST APIs, Docker
LinkedIn: https://linkedin.com/in/sakshisingh
Experience: TechNova Solutions | Senior Software Developer | 2022-06 to present
```

**Output — merged canonical profile (default config):**
```json
{
  "candidate_id": "735f1a22-d1b9-42e7-9fc1-e7f53237df83",
  "full_name": "Sakshi Singh",
  "emails": ["sakshi.s@gmail.com", "sakshi.singh@email.com"],
  "phones": ["+919876543210"],
  "location": { "city": "Jaipur", "region": "Rajasthan", "country": "IN" },
  "headline": "Software Engineer",
  "skills": [
    { "name": "python", "confidence": 1.0, "sources": ["recruiter_csv", "recruiter_notes"] },
    { "name": "docker", "confidence": 1.0, "sources": ["recruiter_csv", "recruiter_notes"] },
    { "name": "git",    "confidence": 0.5, "sources": ["recruiter_csv"] }
  ],
  "overall_confidence": 1.0,
  "provenance": [
    { "field": "full_name", "source": "recruiter_csv", "method": "direct" },
    { "field": "emails",    "source": "recruiter_csv,recruiter_notes", "method": "union_dedup" }
  ]
}
```

**What happened:**
- `full_name` → CSV wins (priority 1)
- `emails` → union from both sources, deduplicated
- `skills` → union; `python` and `docker` appear in both → confidence `1.0`; `git` only in CSV → confidence `0.5`
- `links` → came only from notes (CSV had none) — partial records complement each other
- `provenance` → every field traceable to its source and merge method

---

## Running Tests

```bash
python -m pytest tests/ -v
```

**159 tests — all passing.**

Tests cover: normalizer, merger, notes extractor, output configurator, and validator.

---

## Assumptions

- **Candidate identity**: Matched by exact normalized full name (lowercased, stripped).
- **Source priority**: `recruiter_csv` (priority 1) wins over `recruiter_notes` (priority 2) for conflicting scalar fields.
- **Phone default region**: India (`IN`) — used when no country prefix is present.
- **`years_experience`**: Computed from experience date ranges when not explicitly provided.
- **Skill confidence**: `sources_mentioning_skill / total_sources`.

---

## Future Work

- ATS JSON extractor (additional structured source)
- Resume PDF/DOCX parser
- LinkedIn / GitHub profile extractors
- Configurable source priority via runtime config
- Fuzzy candidate matching for name variations
- Stable candidate IDs using hashing instead of UUID4

---

## Repository Contents

This submission contains:

- ✅ Source code
- ✅ Configuration files (`config/default_config.json`, `config/custom_config.json`)
- ✅ Sample data (`data/sample_candidates.csv`, `data/recruiter_notes.txt`)
- ✅ Generated outputs (`output/default_output.json`, `output/custom_output.json`)
- ✅ Tests (159 passing)
- ✅ Design document (`docs/design_document.md`)

---

For more details on the design decisions, normalization strategies, and conflict resolution policy, see `docs/design_document.md` (one-page technical design).

---

## Conclusion

This project implements a clean, modular candidate data transformer that merges structured and unstructured sources into one canonical profile per candidate. Every field is traceable, every conflict is resolved deterministically, and the output shape is fully configurable at runtime. The implementation prioritizes correctness, clarity, and explainability over breadth.
