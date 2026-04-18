"""Extraction comparator for multi-agent disagreement detection."""

from typing import Any
from lec.extraction.base import ExtractionResult
from lec.provenance import CRITICAL_FIELDS
from lec.core import utc_now_iso


class ExtractionComparator:
    """Compares extractions from multiple agents and identifies disagreements."""

    # Fields to compare (critical fields + additional important fields)
    COMPARE_FIELDS = CRITICAL_FIELDS + [
        "study_id", "nct_id", "pmid", "doi", "n_total"
    ]

    # Tolerance for numeric comparisons
    NUMERIC_TOLERANCE = 0.001

    def compare(self, extraction_a: dict, extraction_b: dict) -> dict:
        """Compare two extractions and return disagreement report."""
        result_a = ExtractionResult(extraction_a)
        result_b = ExtractionResult(extraction_b)

        disagreements = []
        agreements = []

        # Compare top-level fields
        for field in self.COMPARE_FIELDS:
            value_a = self._get_nested_value(result_a.extraction, field)
            value_b = self._get_nested_value(result_b.extraction, field)

            comparison = self._compare_values(field, value_a, value_b)

            if comparison["agrees"]:
                agreements.append({
                    "field": field,
                    "value": value_a
                })
            else:
                disagreements.append({
                    "field": field,
                    "agent_a": {
                        "agent_id": result_a.agent_id,
                        "value": value_a
                    },
                    "agent_b": {
                        "agent_id": result_b.agent_id,
                        "value": value_b
                    },
                    "severity": comparison["severity"],
                    "reason": comparison["reason"]
                })

        # Compare arms
        arms_comparison = self._compare_arms(result_a, result_b)
        disagreements.extend(arms_comparison["disagreements"])
        agreements.extend(arms_comparison["agreements"])

        # Compare outcomes
        outcomes_comparison = self._compare_outcomes(result_a, result_b)
        disagreements.extend(outcomes_comparison["disagreements"])
        agreements.extend(outcomes_comparison["agreements"])

        # Calculate agreement rate
        total = len(disagreements) + len(agreements)
        agreement_rate = len(agreements) / total if total > 0 else 1.0

        return {
            "compared_at": utc_now_iso(),
            "agent_a": result_a.agent_id,
            "agent_b": result_b.agent_id,
            "study_id": result_a.study_id or result_b.study_id,
            "summary": {
                "total_fields": total,
                "agreements": len(agreements),
                "disagreements": len(disagreements),
                "agreement_rate": agreement_rate,
                "critical_disagreements": sum(
                    1 for d in disagreements
                    if d["severity"] == "critical"
                )
            },
            "disagreements": disagreements,
            "agreements": agreements
        }

    def _get_nested_value(self, data: dict, field: str) -> Any:
        """Get value from nested dict using dot notation."""
        if not data:
            return None
        parts = field.split(".")
        value = data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value

    def _compare_values(self, field: str, value_a: Any, value_b: Any) -> dict:
        """Compare two values and return comparison result."""
        # Both None is agreement
        if value_a is None and value_b is None:
            return {"agrees": True, "severity": None, "reason": None}

        # One None is disagreement
        if value_a is None or value_b is None:
            severity = "critical" if field in CRITICAL_FIELDS else "minor"
            return {
                "agrees": False,
                "severity": severity,
                "reason": "one_missing"
            }

        # Numeric comparison with tolerance
        if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
            if abs(value_a - value_b) <= self.NUMERIC_TOLERANCE:
                return {"agrees": True, "severity": None, "reason": None}
            else:
                severity = "critical" if field in CRITICAL_FIELDS else "minor"
                return {
                    "agrees": False,
                    "severity": severity,
                    "reason": f"numeric_difference: {abs(value_a - value_b)}"
                }

        # String comparison (case-insensitive for some fields)
        if isinstance(value_a, str) and isinstance(value_b, str):
            if value_a.lower() == value_b.lower():
                return {"agrees": True, "severity": None, "reason": None}
            else:
                severity = "critical" if field in CRITICAL_FIELDS else "minor"
                return {
                    "agrees": False,
                    "severity": severity,
                    "reason": "string_mismatch"
                }

        # Direct comparison
        if value_a == value_b:
            return {"agrees": True, "severity": None, "reason": None}
        else:
            severity = "critical" if field in CRITICAL_FIELDS else "minor"
            return {
                "agrees": False,
                "severity": severity,
                "reason": "value_mismatch"
            }

    def _compare_arms(self, result_a: ExtractionResult,
                      result_b: ExtractionResult) -> dict:
        """Compare arm data between extractions."""
        disagreements = []
        agreements = []

        arms_a = result_a.extraction.get("arms", [])
        arms_b = result_b.extraction.get("arms", [])

        # Index by label
        arms_a_by_label = {a.get("label"): a for a in arms_a}
        arms_b_by_label = {b.get("label"): b for b in arms_b}

        all_labels = set(arms_a_by_label.keys()) | set(arms_b_by_label.keys())

        for label in all_labels:
            arm_a = arms_a_by_label.get(label)
            arm_b = arms_b_by_label.get(label)

            if arm_a and arm_b:
                # Compare N
                n_a = arm_a.get("n")
                n_b = arm_b.get("n")
                if n_a != n_b:
                    disagreements.append({
                        "field": f"arms.{label}.n",
                        "agent_a": {"agent_id": result_a.agent_id, "value": n_a},
                        "agent_b": {"agent_id": result_b.agent_id, "value": n_b},
                        "severity": "critical",
                        "reason": "arm_n_mismatch"
                    })
                else:
                    agreements.append({"field": f"arms.{label}.n", "value": n_a})

                # Compare events if present
                events_a = arm_a.get("events")
                events_b = arm_b.get("events")
                if events_a is not None or events_b is not None:
                    if events_a != events_b:
                        disagreements.append({
                            "field": f"arms.{label}.events",
                            "agent_a": {"agent_id": result_a.agent_id, "value": events_a},
                            "agent_b": {"agent_id": result_b.agent_id, "value": events_b},
                            "severity": "critical",
                            "reason": "arm_events_mismatch"
                        })
                    else:
                        agreements.append({"field": f"arms.{label}.events", "value": events_a})
            else:
                # One agent missing this arm
                disagreements.append({
                    "field": f"arms.{label}",
                    "agent_a": {"agent_id": result_a.agent_id, "value": arm_a},
                    "agent_b": {"agent_id": result_b.agent_id, "value": arm_b},
                    "severity": "critical",
                    "reason": "arm_missing"
                })

        return {"disagreements": disagreements, "agreements": agreements}

    def _compare_outcomes(self, result_a: ExtractionResult,
                          result_b: ExtractionResult) -> dict:
        """Compare outcome data between extractions."""
        disagreements = []
        agreements = []

        outcomes_a = result_a.extraction.get("outcomes", [])
        outcomes_b = result_b.extraction.get("outcomes", [])

        # Index by name
        outcomes_a_by_name = {o.get("name"): o for o in outcomes_a}
        outcomes_b_by_name = {o.get("name"): o for o in outcomes_b}

        all_names = set(outcomes_a_by_name.keys()) | set(outcomes_b_by_name.keys())

        for name in all_names:
            outcome_a = outcomes_a_by_name.get(name)
            outcome_b = outcomes_b_by_name.get(name)

            if outcome_a and outcome_b:
                # Compare effect estimates
                effect_a = outcome_a.get("effect", {})
                effect_b = outcome_b.get("effect", {})

                for field in ["estimate", "ci_low", "ci_high", "measure"]:
                    val_a = effect_a.get(field)
                    val_b = effect_b.get(field)
                    comparison = self._compare_values(f"effect_{field}", val_a, val_b)

                    if comparison["agrees"]:
                        agreements.append({
                            "field": f"outcomes.{name}.effect.{field}",
                            "value": val_a
                        })
                    else:
                        disagreements.append({
                            "field": f"outcomes.{name}.effect.{field}",
                            "agent_a": {"agent_id": result_a.agent_id, "value": val_a},
                            "agent_b": {"agent_id": result_b.agent_id, "value": val_b},
                            "severity": comparison["severity"],
                            "reason": comparison["reason"]
                        })
            else:
                disagreements.append({
                    "field": f"outcomes.{name}",
                    "agent_a": {"agent_id": result_a.agent_id, "value": outcome_a is not None},
                    "agent_b": {"agent_id": result_b.agent_id, "value": outcome_b is not None},
                    "severity": "critical",
                    "reason": "outcome_missing"
                })

        return {"disagreements": disagreements, "agreements": agreements}
