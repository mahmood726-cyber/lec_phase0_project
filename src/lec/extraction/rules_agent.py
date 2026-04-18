"""Rules-based extraction agent (Agent A).

Deterministic extractor using pattern matching and heuristics.
"""

import re
from pathlib import Path

from lec.extraction.base import BaseExtractor
from lec.provenance import ProvenanceTracker, CRITICAL_FIELDS
from lec.core import make_trial_key


class RulesExtractor(BaseExtractor):
    """Deterministic rules-based extractor."""

    agent_id = "rules_v1"
    agent_type = "rules"

    # Patterns for extracting data
    PATTERNS = {
        "nct_id": re.compile(r"NCT\d{8}", re.IGNORECASE),
        "pmid": re.compile(r"PMID[:\s]*(\d+)", re.IGNORECASE),
        "doi": re.compile(r"10\.\d{4,}/[^\s]+"),
        "n_total": re.compile(r"(?:n\s*=\s*|enrolled\s+)(\d+)", re.IGNORECASE),
        "n_arm": re.compile(r"(\d+)\s+(?:patients?|participants?|subjects?)", re.IGNORECASE),
        "events": re.compile(r"(\d+)\s+(?:events?|deaths?|outcomes?)", re.IGNORECASE),
        "ratio": re.compile(r"(?:OR|RR|HR)[:\s=]*(\d+\.?\d*)\s*[\[(](\d+\.?\d*)[,\-–](\d+\.?\d*)[\])]", re.IGNORECASE),
        "ci": re.compile(r"95%?\s*CI[:\s]*[\[(]?(\d+\.?\d*)[,\-–]\s*(\d+\.?\d*)[\])]?", re.IGNORECASE),
        "p_value": re.compile(r"p\s*[=<>]\s*(\d*\.?\d+)", re.IGNORECASE),
    }

    def extract(self, source_path: Path) -> dict:
        """Extract data from source using rules."""
        # Read source content
        content = self._read_source(source_path)

        # Extract identifiers
        nct_id = self._extract_pattern("nct_id", content)
        pmid = self._extract_pattern("pmid", content)
        doi = self._extract_pattern("doi", content)

        # Generate study ID
        study_id = make_trial_key(nct_id=nct_id, pmid=pmid, doi=doi,
                                   raw_label=source_path.stem)

        # Initialize provenance tracker
        provenance = ProvenanceTracker(study_id)

        # Extract study data
        extraction = {
            "study_id": study_id,
            "nct_id": nct_id,
            "pmid": pmid,
            "doi": doi,
            "n_total": self._extract_int("n_total", content),
            "arms": self._extract_arms(content, provenance, source_path),
            "outcomes": self._extract_outcomes(content, provenance, source_path),
        }

        # Add provenance for top-level fields
        if nct_id:
            provenance.add_field("nct_id", nct_id, str(source_path), "file",
                                  self.agent_id, "regex")
        if extraction["n_total"]:
            provenance.add_field("n", extraction["n_total"], str(source_path), "file",
                                  self.agent_id, "regex")

        return self._make_extraction_result(study_id, extraction, provenance, source_path)

    def _read_source(self, source_path: Path) -> str:
        """Read source file content."""
        if source_path.suffix.lower() == ".json":
            import json
            with open(source_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data)
        else:
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

    def _extract_pattern(self, pattern_name: str, content: str) -> str | None:
        """Extract first match of named pattern."""
        pattern = self.PATTERNS.get(pattern_name)
        if not pattern:
            return None
        match = pattern.search(content)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
        return None

    def _extract_int(self, pattern_name: str, content: str) -> int | None:
        """Extract integer from pattern match."""
        value = self._extract_pattern(pattern_name, content)
        if value:
            try:
                return int(value)
            except ValueError:
                pass
        return None

    def _extract_arms(self, content: str, provenance: ProvenanceTracker,
                      source_path: Path) -> list[dict]:
        """Extract arm data."""
        arms = []

        # Look for treatment/control patterns
        treatment_patterns = [
            r"treatment\s+(?:group|arm)[:\s]*n\s*=\s*(\d+)",
            r"(\d+)\s+(?:in|received)\s+(?:treatment|intervention|colchicine)",
        ]
        control_patterns = [
            r"(?:control|placebo)\s+(?:group|arm)[:\s]*n\s*=\s*(\d+)",
            r"(\d+)\s+(?:in|received)\s+(?:control|placebo)",
        ]

        for pattern in treatment_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                n = int(match.group(1))
                arms.append({
                    "label": "treatment",
                    "n": n,
                    "role": "intervention"
                })
                provenance.add_field("arm_label", "treatment", str(source_path),
                                      "file", self.agent_id, "regex")
                provenance.add_field("n", n, str(source_path), "file",
                                      self.agent_id, "regex")
                break

        for pattern in control_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                n = int(match.group(1))
                arms.append({
                    "label": "control",
                    "n": n,
                    "role": "comparator"
                })
                provenance.add_field("arm_label", "control", str(source_path),
                                      "file", self.agent_id, "regex")
                break

        return arms

    def _extract_outcomes(self, content: str, provenance: ProvenanceTracker,
                          source_path: Path) -> list[dict]:
        """Extract outcome data."""
        outcomes = []

        # Look for effect estimates
        ratio_match = self.PATTERNS["ratio"].search(content)
        if ratio_match:
            estimate = float(ratio_match.group(1))
            ci_low = float(ratio_match.group(2))
            ci_high = float(ratio_match.group(3))

            # Determine measure type from context
            measure = "OR"
            if "hazard" in content.lower():
                measure = "HR"
            elif "risk ratio" in content.lower() or "relative risk" in content.lower():
                measure = "RR"

            outcome = {
                "name": "primary",
                "type": "binary",
                "effect": {
                    "measure": measure,
                    "estimate": estimate,
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                },
                "effect_direction": "treatment" if estimate < 1 else "control"
            }
            outcomes.append(outcome)

            # Add provenance
            provenance.add_field("outcome_name", "primary", str(source_path),
                                  "file", self.agent_id, "rules")
            provenance.add_field("effect_estimate", estimate, str(source_path),
                                  "file", self.agent_id, "regex")
            provenance.add_field("effect_ci_low", ci_low, str(source_path),
                                  "file", self.agent_id, "regex")
            provenance.add_field("effect_ci_high", ci_high, str(source_path),
                                  "file", self.agent_id, "regex")
            provenance.add_field("effect_direction",
                                  "treatment" if estimate < 1 else "control",
                                  str(source_path), "file", self.agent_id, "rules")

        return outcomes
