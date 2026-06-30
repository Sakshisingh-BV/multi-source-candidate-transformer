"""Abstract base class for all source extractors."""

from abc import ABC, abstractmethod
from src.models import RawRecord


class BaseExtractor(ABC):
    """Every extractor must implement extract() and return a list of RawRecords
    (one per candidate row / block found in the source)."""

    @abstractmethod
    def extract(self, file_path: str) -> list[RawRecord]:
        """Parse file_path and return raw records. Must never raise —
        catch all errors internally and surface them via RawRecord.errors."""
