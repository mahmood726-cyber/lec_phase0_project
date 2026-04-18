"""Base validator class."""

from abc import ABC, abstractmethod
from typing import Any

from lec.core import utc_now_iso


class BaseValidator(ABC):
    """Abstract base class for validators."""

    name: str = "base"
    description: str = "Base validator"

    @abstractmethod
    def validate(self, extraction_data: dict) -> dict:
        """Validate extraction data.

        Returns:
            dict with keys:
                - validator: str (validator name)
                - status: str (PASS | FLAG | FAIL)
                - issues: list[dict] (list of issues found)
                - validated_at: str (ISO timestamp)
        """
        pass

    def _make_result(self, status: str, issues: list[dict]) -> dict:
        """Create standardized result dict."""
        return {
            "validator": self.name,
            "description": self.description,
            "status": status,
            "issues": issues,
            "issue_count": len(issues),
            "validated_at": utc_now_iso()
        }

    def _make_issue(self, study_id: str, field: str, message: str,
                    severity: str = "warning", details: dict = None) -> dict:
        """Create standardized issue dict."""
        issue = {
            "study_id": study_id,
            "field": field,
            "message": message,
            "severity": severity  # error | warning | info
        }
        if details:
            issue["details"] = details
        return issue
