# Multi-Source Candidate Data Transformer — Technical Design
**Sakshi Singh · Eightfold AI Assignment**

---

## 1. Problem Statement
Candidate data arrives from structured and unstructured sources with conflicting values. The system produces a single canonical profile using deterministic normalization, conflict resolution, provenance tracking, and configurable output.

---

## 2. System Architecture
The end-to-end flow from input source ingestion down to schema-validated JSON:

<div align="center">

```mermaid
flowchart TD
    %% Source Ingestion
    A[Recruiter CSV]
    B[Recruiter Notes]

    %% Pipeline Steps
    C[Extractors]
    D[Normalizer]
    E["Merger<br>Priority • Union<br>Provenance"]
    F[Output Config]
    G[Validator]

    %% Branched Outputs
    H[Default Output]
    I[Custom Output]

    %% Connections
    A --> C
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    G --> I

    %% Color & Node Styling
    style A fill:#1e3a8a,stroke:#3b82f6,stroke-width:2px,color:#eff6ff
    style B fill:#2d1f4e,stroke:#6b46c1,stroke-width:2px,color:#d6bcfa
    
    style C fill:#1e293b,stroke:#475569,stroke-width:2px,color:#f8fafc
    style D fill:#1e293b,stroke:#475569,stroke-width:2px,color:#f8fafc
    style E fill:#2d2a1f,stroke:#b7791f,stroke-width:2px,color:#f6e05e
    style F fill:#1e293b,stroke:#475569,stroke-width:2px,color:#f8fafc
    style G fill:#1e293b,stroke:#475569,stroke-width:2px,color:#f8fafc

    style H fill:#1c1917,stroke:#78716c,stroke-width:2px,color:#e7e5e4
    style I fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#ecfdf5

    classDef default font-family:Inter,font-weight:bold;
```

</div>

---

## 3. Merge Strategy & Confidence
Conflicting fields are merged deterministically using fixed priority rules, and overall confidence is computed based on profile completeness:

```mermaid
flowchart TD
    subgraph Inputs
        A[CSV Sources]
        B[Notes Sources]
    end

    subgraph Merge Engine
        C{Field Type?}
        D[Scalars: Source Priority Win]
        E[Lists: Union & Deduplicate]
        F[Skills: Mention Count Confidence]
    end

    A --> C
    B --> C
    C --> D
    C --> E
    C --> F

    D --> G[Canonical Profile + Provenance]
    E --> G
    F --> G
```

- **Scalar Fields**: Higher-priority source wins.
- **List Fields**: Union + Deduplicate.
- **Skills**: confidence = sources mentioning skill / total sources.
- **Overall Confidence**: populated key fields / total key fields.

---

## 4. Runtime Configuration & Projection
A runtime JSON configuration reshapes the output layout dynamically without requiring codebase changes:

```mermaid
flowchart LR
    A[Canonical Profile] --> B[Runtime Config Engine]
    B --> C{on_missing Policy}
    C -->|default| D[Default Output: Full Schema]
    C -->|custom| E[Custom Output: Config Projection]
    
    style B fill:#2d1f4e,stroke:#6b46c1,color:#d6bcfa
```

- **Default Config**: Emits all canonical fields, including complete provenance and confidence metrics.
- **Custom Config**: Evaluates path expressions (e.g., `emails[0]`, `skills[].name`), selects specific fields, renames keys, and toggles metadata.

---

## 5. Normalization Strategy & Canonical Schema

### Formats
- **Phone**: E.164 (e.g. `+919876543210`) via `phonenumbers`.
- **Dates**: YYYY-MM (e.g. `2025-06`) via `python-dateutil`.
- **Country**: ISO-3166 alpha-2 (e.g. `IN`) via lookup.
- **Skills**: Lowercased canonical synonyms (e.g. `js` &rarr; `javascript`).

### Key Schema Fields
- `candidate_id` (UUID4)
- `full_name`
- `emails`
- `phones`
- `location` (city, region, country)
- `links` (linkedin, github, portfolio, other)
- `headline`
- `years_experience`
- `skills` (name, confidence, sources)
- `experience` (company, title, start, end, summary)
- `education` (institution, degree, field, end_year)
- `provenance` (field, source, method)
- `overall_confidence`

---

## 6. Edge Cases

- **Missing / Malformed Source**: Extractor captures exceptions safely and surfaces a warning without crashing.
- **Conflicting Values**: Deterministic source priority ensures the most reliable values win.
- **Partial Records**: Sources automatically complement one another to fill missing fields.
- **Skill Synonyms**: Synonyms mapped to canonical forms prior to merging.

---

## 7. Scope Decisions & Future Work

### Implemented (Current Scope)
- **Recruiter CSV**: Structured source ingestion.
- **Recruiter Notes**: Unstructured source block-extraction.
- **Data normalization**: Standardized formats for phones, dates, countries, and skills.
- **Conflict resolution**: Priority-based merging tracking provenance.
- **Confidence scoring**: Scoring profile completeness and skill frequency.
- **Runtime configurable output**: Target field mapping and schema projection.
- **Schema validation**: Dynamic output schema generation and validation.
- **Graceful degradation**: Individual source failures do not terminate the pipeline; valid sources continue to be processed.

### Future Work
- **ATS JSON extractor**: Integration of additional structured candidate payloads.
- **Resume PDF/DOCX parser**: Text mining from uploaded documents.
- **LinkedIn / GitHub profile extractors**: Automated data fetching via public APIs.
- **Configurable source priority**: Externalizing the source trust order to the config.
- **Fuzzy candidate matching**: Phonetic or edit-distance clustering for name variations.
- **Stable candidate IDs**: Generating repeatable candidate hashes instead of random UUIDs.

These enhancements were intentionally left out to keep the implementation focused on the assignment requirements while maintaining a clean, modular, and explainable design.


