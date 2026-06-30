"""CSV extractor — parses recruiter CSV exports into RawRecords."""

import csv
from src.extractors.base import BaseExtractor
from src.models import RawRecord

SOURCE_ID = "recruiter_csv"


class CsvExtractor(BaseExtractor):
    """Reads a CSV file where each row is one candidate.
    Field names are kept as-is; normalization happens in normalizer.py."""

    def extract(self, file_path: str) -> list[RawRecord]:
        records: list[RawRecord] = []
        try:
            with open(file_path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for i, row in enumerate(reader):
                    # Skip completely empty rows
                    if not any(row.values()):
                        continue
                    records.append(
                        RawRecord(
                            source_id=SOURCE_ID,
                            source_type="structured",
                            data={k.strip(): v.strip() for k, v in row.items() if k},
                        )
                    )
        except FileNotFoundError:
            records.append(
                RawRecord(
                    source_id=SOURCE_ID,
                    source_type="structured",
                    data={},
                    errors=[f"File not found: {file_path}"],
                )
            )
        except Exception as exc:  # malformed CSV, encoding errors, etc.
            records.append(
                RawRecord(
                    source_id=SOURCE_ID,
                    source_type="structured",
                    data={},
                    errors=[f"Failed to parse {file_path}: {exc}"],
                )
            )
        return records
