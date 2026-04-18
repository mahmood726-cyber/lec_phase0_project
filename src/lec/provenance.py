"""Provenance tracking for critical effect-changing fields.

Critical fields requiring provenance (per CLAUDE.md):
- arm labels
- N/events
- outcome name
- timepoint
- units
- effect direction cues
- source locator
"""

from dataclasses import dataclass, field, asdict
from typing import Any
from lec.core import utc_now_iso, sha256_string


# Critical fields that MUST have provenance
CRITICAL_FIELDS = [
    "arm_label",
    "n",
    "events",
    "outcome_name",
    "timepoint",
    "timepoint_unit",
    "units",
    "effect_direction",
    "effect_estimate",
    "effect_ci_low",
    "effect_ci_high",
]


@dataclass
class SourceLocator:
    """Locator for source of extracted data."""
    source_id: str  # PMCID, DOI, PDF hash, etc.
    source_type: str  # pdf, html, json, api
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None  # x1, y1, x2, y2
    section: str | None = None
    table_id: str | None = None
    paragraph: int | None = None

    def to_dict(self) -> dict:
        result = {
            "source_id": self.source_id,
            "source_type": self.source_type,
        }
        if self.page is not None:
            result["page"] = self.page
        if self.bbox is not None:
            result["bbox"] = list(self.bbox)
        if self.section:
            result["section"] = self.section
        if self.table_id:
            result["table_id"] = self.table_id
        if self.paragraph is not None:
            result["paragraph"] = self.paragraph
        return result


@dataclass
class Provenance:
    """Provenance record for a single field extraction."""
    field_name: str
    value: Any
    source: SourceLocator
    agent_id: str  # Identifier of extraction agent
    method: str  # rules, llm, manual, etc.
    confidence: float | None = None  # 0.0-1.0 if available
    extracted_at: str = field(default_factory=utc_now_iso)
    raw_text: str | None = None  # Original text from source

    def to_dict(self) -> dict:
        result = {
            "field_name": self.field_name,
            "value": self.value,
            "source": self.source.to_dict(),
            "agent_id": self.agent_id,
            "method": self.method,
            "extracted_at": self.extracted_at,
        }
        if self.confidence is not None:
            result["confidence"] = self.confidence
        if self.raw_text:
            result["raw_text"] = self.raw_text
        return result

    def hash(self) -> str:
        """Generate hash of provenance content."""
        content = f"{self.field_name}:{self.value}:{self.source.source_id}:{self.agent_id}"
        return sha256_string(content)[:16]


class ProvenanceTracker:
    """Tracks provenance for all extracted fields."""

    def __init__(self, study_id: str):
        self.study_id = study_id
        self.records: dict[str, Provenance] = {}
        self.created_at = utc_now_iso()

    def add(self, provenance: Provenance) -> None:
        """Add provenance record for a field."""
        key = f"{provenance.field_name}"
        self.records[key] = provenance

    def add_field(
        self,
        field_name: str,
        value: Any,
        source_id: str,
        source_type: str,
        agent_id: str,
        method: str,
        page: int | None = None,
        bbox: tuple | None = None,
        confidence: float | None = None,
        raw_text: str | None = None,
    ) -> None:
        """Convenience method to add provenance for a field."""
        source = SourceLocator(
            source_id=source_id,
            source_type=source_type,
            page=page,
            bbox=bbox,
        )
        
        # Redact sensitive info from raw_text
        redacted_text = self._redact_sensitive(raw_text) if raw_text else None
        
        provenance = Provenance(
            field_name=field_name,
            value=value,
            source=source,
            agent_id=agent_id,
            method=method,
            confidence=confidence,
            raw_text=redacted_text,
        )
        self.add(provenance)

    def _redact_sensitive(self, text: str) -> str:
        """Redact potential local paths and sensitive info from text."""
        import re
        # Basic redaction for Windows/Unix paths
        path_pattern = r'[a-zA-Z]:\\[\\\w\s.-]+|/[/\w\s.-]+'
        return re.sub(path_pattern, "[PATH_REDACTED]", text)

    def get(self, field_name: str) -> Provenance | None:
        """Get provenance for a field."""
        return self.records.get(field_name)

    def validate_critical_fields(self, extracted_data: dict) -> list[str]:
        """Check that all critical fields have provenance. Returns missing fields."""
        missing = []

        for field in CRITICAL_FIELDS:
            # Check if field exists in extracted data
            if self._field_exists(field, extracted_data):
                # Check if provenance exists
                if field not in self.records:
                    missing.append(field)

        return missing

    def _field_exists(self, field_name: str, data: dict) -> bool:
        """Check if a critical field exists in extracted data."""
        # Handle nested fields
        if field_name in data and data[field_name] is not None:
            return True

        # Check in arms
        for arm in data.get("arms", []):
            if field_name in arm and arm[field_name] is not None:
                return True

        # Check in outcomes
        for outcome in data.get("outcomes", []):
            if field_name in outcome and outcome[field_name] is not None:
                return True
            # Check effect subfields
            effect = outcome.get("effect", {})
            if field_name.startswith("effect_"):
                subfield = field_name.replace("effect_", "")
                if subfield in effect and effect[subfield] is not None:
                    return True

        return False

    def to_dict(self) -> dict:
        """Export provenance tracker to dictionary."""
        return {
            "study_id": self.study_id,
            "created_at": self.created_at,
            "record_count": len(self.records),
            "records": {k: v.to_dict() for k, v in self.records.items()}
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProvenanceTracker":
        """Create tracker from dictionary."""
        # Handle cases where data might be the records dict itself
        if "study_id" not in data:
            # Look for records key, if not there, assume data is the records
            records_data = data.get("records", data)
            study_id = data.get("study_id", "unknown")
        else:
            study_id = data["study_id"]
            records_data = data.get("records", {})

        tracker = cls(study_id)
        tracker.created_at = data.get("created_at", utc_now_iso())

        for key, record_data in records_data.items():
            if not isinstance(record_data, dict) or "source" not in record_data:
                continue
                
            source_data = record_data["source"]
            source = SourceLocator(
                source_id=source_data.get("source_id", "unknown"),
                source_type=source_data.get("source_type", "unknown"),
                page=source_data.get("page"),
                bbox=tuple(source_data["bbox"]) if source_data.get("bbox") else None,
                section=source_data.get("section"),
                table_id=source_data.get("table_id"),
            )
            provenance = Provenance(
                field_name=record_data.get("field_name", key),
                value=record_data.get("value"),
                source=source,
                agent_id=record_data.get("agent_id", "unknown"),
                method=record_data.get("method", "unknown"),
                confidence=record_data.get("confidence"),
                extracted_at=record_data.get("extracted_at", utc_now_iso()),
                raw_text=record_data.get("raw_text"),
            )
            tracker.records[key] = provenance

        return tracker


class ProvenanceValidator:
    """Validates that critical fields have provenance."""

    def validate(self, extraction_data: dict) -> dict:
        """Validate provenance for all studies in extraction."""
        issues = []
        studies = extraction_data.get("studies", [])

        for study in studies:
            study_id = study.get("study_id", "unknown")
            provenance_data = study.get("provenance", {})

            if not provenance_data:
                issues.append({
                    "study_id": study_id,
                    "severity": "error",
                    "message": "No provenance data found for study"
                })
                continue

            tracker = ProvenanceTracker.from_dict(provenance_data) if isinstance(provenance_data, dict) else None

            if tracker:
                missing = tracker.validate_critical_fields(study)
                for field in missing:
                    issues.append({
                        "study_id": study_id,
                        "field": field,
                        "severity": "error",
                        "message": f"Critical field '{field}' missing provenance"
                    })

        return {
            "validator": "provenance",
            "status": "FAIL" if any(i["severity"] == "error" for i in issues) else "PASS",
            "issues": issues,
            "issue_count": len(issues)
        }
