"""Base extractor class."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from lec.core import utc_now_iso
from lec.provenance import ProvenanceTracker


class BaseExtractor(ABC):
    """Abstract base class for extraction agents."""

    agent_id: str = "base"
    agent_type: str = "abstract"

    @abstractmethod
    def extract(self, source_path: Path) -> dict:
        """Extract data from source document.

        Returns:
            dict with keys:
                - study_id: str
                - extraction: dict (extracted data)
                - provenance: dict (provenance tracker data)
                - metadata: dict (extraction metadata)
        """
        pass

    def _make_extraction_result(
        self,
        study_id: str,
        extraction: dict,
        provenance: ProvenanceTracker,
        source_path: Path,
    ) -> dict:
        """Create standardized extraction result."""
        return {
            "study_id": study_id,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "source_path": str(source_path),
            "extracted_at": utc_now_iso(),
            "extraction": extraction,
            "provenance": provenance.to_dict(),
        }


class ExtractionResult:
    """Wrapper for extraction results with comparison support."""

    def __init__(self, data: dict):
        self.study_id = data.get("study_id")
        self.agent_id = data.get("agent_id")
        self.agent_type = data.get("agent_type")
        self.source_path = data.get("source_path")
        self.extracted_at = data.get("extracted_at")
        self.extraction = data.get("extraction", {})
        self.provenance = data.get("provenance", {})

    def get_field(self, field_path: str) -> Any:
        """Get field value by dot-notation path."""
        parts = field_path.split(".")
        value = self.extraction
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit():
                idx = int(part)
                value = value[idx] if idx < len(value) else None
            else:
                return None
        return value

    def to_dict(self) -> dict:
        return {
            "study_id": self.study_id,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "source_path": self.source_path,
            "extracted_at": self.extracted_at,
            "extraction": self.extraction,
            "provenance": self.provenance,
        }
