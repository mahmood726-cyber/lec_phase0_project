"""Extraction Accuracy Validator.

Validates extraction accuracy against gold-standard manual extraction.
Calculates sensitivity, specificity, and error rates per field type.
"""

from typing import Any
from lec.validators.base import BaseValidator
from lec.core import utc_now_iso


class ExtractionAccuracyValidator(BaseValidator):
    """Validates extraction against gold-standard reference."""

    name = "extraction_accuracy"
    description = "Validates extraction accuracy against gold-standard"

    # Tolerance for numeric fields
    NUMERIC_TOLERANCE = {
        "n": 0,  # Exact match required
        "events": 0,  # Exact match required
        "estimate": 0.01,  # 1% tolerance
        "ci_low": 0.01,
        "ci_high": 0.01,
        "timepoint": 0.1,
    }

    # Field weights for overall accuracy score
    FIELD_WEIGHTS = {
        "n": 1.0,
        "events": 1.0,
        "estimate": 1.5,  # Higher weight for effect estimate
        "ci_low": 1.0,
        "ci_high": 1.0,
        "effect_direction": 1.5,
        "arm_label": 0.5,
        "outcome_name": 0.5,
    }

    def validate(self, extraction_data: dict, gold_standard: dict = None) -> dict:
        """Validate extraction against gold standard.

        Args:
            extraction_data: Extracted data to validate
            gold_standard: Gold-standard reference data (manual extraction)

        Returns:
            Validation result with accuracy metrics
        """
        issues = []
        metrics = {
            "total_fields": 0,
            "correct_fields": 0,
            "incorrect_fields": 0,
            "missing_fields": 0,
            "extra_fields": 0,
            "field_errors": {},
            "per_study_accuracy": [],
        }

        if not gold_standard:
            # No gold standard provided - check internal consistency only
            return self._validate_internal_consistency(extraction_data)

        # Compare each study
        extracted_studies = {s.get("study_id"): s for s in extraction_data.get("studies", [])}
        gold_studies = {s.get("study_id"): s for s in gold_standard.get("studies", [])}

        all_study_ids = set(extracted_studies.keys()) | set(gold_studies.keys())

        for study_id in all_study_ids:
            extracted = extracted_studies.get(study_id)
            gold = gold_studies.get(study_id)

            if not gold:
                issues.append(self._make_issue(
                    study_id, "study", f"Extra study not in gold standard",
                    severity="warning"
                ))
                metrics["extra_fields"] += 1
                continue

            if not extracted:
                issues.append(self._make_issue(
                    study_id, "study", f"Missing study from extraction",
                    severity="error"
                ))
                metrics["missing_fields"] += 1
                continue

            # Compare fields
            study_metrics = self._compare_study(study_id, extracted, gold, issues)
            metrics["per_study_accuracy"].append({
                "study_id": study_id,
                **study_metrics
            })
            metrics["total_fields"] += study_metrics["total"]
            metrics["correct_fields"] += study_metrics["correct"]
            metrics["incorrect_fields"] += study_metrics["incorrect"]

        # Calculate overall metrics
        if metrics["total_fields"] > 0:
            metrics["overall_accuracy"] = metrics["correct_fields"] / metrics["total_fields"]
            metrics["error_rate"] = metrics["incorrect_fields"] / metrics["total_fields"]
        else:
            metrics["overall_accuracy"] = 0
            metrics["error_rate"] = 1.0

        # Calculate per-field sensitivity/specificity
        metrics["field_metrics"] = self._calculate_field_metrics(
            extraction_data, gold_standard
        )

        # Determine status based on accuracy threshold
        if metrics["overall_accuracy"] >= 0.95:
            status = "PASS"
        elif metrics["overall_accuracy"] >= 0.85:
            status = "FLAG"
        else:
            status = "FAIL"

        result = self._make_result(status, issues)
        result["metrics"] = metrics
        return result

    def _validate_internal_consistency(self, extraction_data: dict) -> dict:
        """Validate internal consistency when no gold standard available."""
        issues = []
        studies = extraction_data.get("studies", [])

        for study in studies:
            study_id = study.get("study_id", "unknown")

            # Check required fields present
            required = ["study_id", "arms", "outcomes"]
            for field in required:
                if not study.get(field):
                    issues.append(self._make_issue(
                        study_id, field, f"Required field '{field}' missing",
                        severity="error"
                    ))

            # Check arms have required data
            for arm in study.get("arms", []):
                if not arm.get("label"):
                    issues.append(self._make_issue(
                        study_id, "arm_label", "Arm missing label",
                        severity="error"
                    ))
                if arm.get("n") is None:
                    issues.append(self._make_issue(
                        study_id, "arm_n", "Arm missing N",
                        severity="warning"
                    ))

            # Check outcomes have effect estimates
            for outcome in study.get("outcomes", []):
                effect = outcome.get("effect", {})
                if effect.get("estimate") is None:
                    issues.append(self._make_issue(
                        study_id, "effect_estimate",
                        f"Outcome '{outcome.get('name')}' missing effect estimate",
                        severity="error"
                    ))

        status = "FAIL" if any(i["severity"] == "error" for i in issues) else "PASS"
        result = self._make_result(status, issues)
        result["metrics"] = {"validation_type": "internal_consistency"}
        return result

    def _compare_study(self, study_id: str, extracted: dict, gold: dict,
                       issues: list) -> dict:
        """Compare extracted study against gold standard."""
        metrics = {"total": 0, "correct": 0, "incorrect": 0, "field_errors": {}}

        # Compare top-level fields
        for field in ["n_total", "year"]:
            metrics["total"] += 1
            ext_val = extracted.get(field)
            gold_val = gold.get(field)

            if self._values_match(field, ext_val, gold_val):
                metrics["correct"] += 1
            else:
                metrics["incorrect"] += 1
                metrics["field_errors"][field] = {
                    "extracted": ext_val, "gold": gold_val
                }
                issues.append(self._make_issue(
                    study_id, field,
                    f"Mismatch: extracted={ext_val}, gold={gold_val}",
                    severity="error"
                ))

        # Compare arms
        ext_arms = {a.get("label"): a for a in extracted.get("arms", [])}
        gold_arms = {a.get("label"): a for a in gold.get("arms", [])}

        for label in set(ext_arms.keys()) | set(gold_arms.keys()):
            ext_arm = ext_arms.get(label, {})
            gold_arm = gold_arms.get(label, {})

            for field in ["n", "events"]:
                metrics["total"] += 1
                ext_val = ext_arm.get(field)
                gold_val = gold_arm.get(field)

                if self._values_match(field, ext_val, gold_val):
                    metrics["correct"] += 1
                else:
                    metrics["incorrect"] += 1
                    key = f"arm_{label}_{field}"
                    metrics["field_errors"][key] = {
                        "extracted": ext_val, "gold": gold_val
                    }
                    if gold_val is not None:
                        issues.append(self._make_issue(
                            study_id, key,
                            f"Arm '{label}' {field}: extracted={ext_val}, gold={gold_val}",
                            severity="error"
                        ))

        # Compare outcomes
        ext_outcomes = {o.get("name"): o for o in extracted.get("outcomes", [])}
        gold_outcomes = {o.get("name"): o for o in gold.get("outcomes", [])}

        for name in set(ext_outcomes.keys()) | set(gold_outcomes.keys()):
            ext_out = ext_outcomes.get(name, {})
            gold_out = gold_outcomes.get(name, {})
            ext_effect = ext_out.get("effect", {})
            gold_effect = gold_out.get("effect", {})

            for field in ["estimate", "ci_low", "ci_high"]:
                metrics["total"] += 1
                ext_val = ext_effect.get(field)
                gold_val = gold_effect.get(field)

                if self._values_match(field, ext_val, gold_val):
                    metrics["correct"] += 1
                else:
                    metrics["incorrect"] += 1
                    key = f"outcome_{name}_{field}"
                    metrics["field_errors"][key] = {
                        "extracted": ext_val, "gold": gold_val
                    }
                    if gold_val is not None:
                        issues.append(self._make_issue(
                            study_id, key,
                            f"Outcome '{name}' {field}: extracted={ext_val}, gold={gold_val}",
                            severity="error"
                        ))

        return metrics

    def _values_match(self, field: str, extracted: Any, gold: Any) -> bool:
        """Check if extracted value matches gold standard within tolerance."""
        if extracted is None and gold is None:
            return True
        if extracted is None or gold is None:
            return False

        # Numeric comparison with tolerance
        if isinstance(gold, (int, float)) and isinstance(extracted, (int, float)):
            tolerance = self.NUMERIC_TOLERANCE.get(field, 0.01)
            if tolerance == 0:
                return extracted == gold
            return abs(extracted - gold) <= abs(gold * tolerance)

        # String comparison (case-insensitive)
        if isinstance(gold, str) and isinstance(extracted, str):
            return extracted.lower().strip() == gold.lower().strip()

        return extracted == gold

    def _calculate_field_metrics(self, extraction: dict, gold: dict) -> dict:
        """Calculate sensitivity/specificity per field type."""
        field_stats = {}

        # Aggregate all field comparisons
        for field_type in ["n", "events", "estimate", "ci_low", "ci_high"]:
            tp = fp = fn = tn = 0

            ext_studies = extraction.get("studies", [])
            gold_studies = {s["study_id"]: s for s in gold.get("studies", [])}

            for ext_study in ext_studies:
                study_id = ext_study.get("study_id")
                gold_study = gold_studies.get(study_id, {})

                ext_val = self._get_field_value(ext_study, field_type)
                gold_val = self._get_field_value(gold_study, field_type)

                if gold_val is not None:
                    if ext_val is not None and self._values_match(field_type, ext_val, gold_val):
                        tp += 1
                    elif ext_val is not None:
                        fp += 1
                    else:
                        fn += 1
                else:
                    if ext_val is None:
                        tn += 1
                    else:
                        fp += 1

            sensitivity = tp / (tp + fn) if (tp + fn) > 0 else None
            specificity = tn / (tn + fp) if (tn + fp) > 0 else None
            precision = tp / (tp + fp) if (tp + fp) > 0 else None

            field_stats[field_type] = {
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "true_negatives": tn,
                "sensitivity": round(sensitivity, 4) if sensitivity else None,
                "specificity": round(specificity, 4) if specificity else None,
                "precision": round(precision, 4) if precision else None,
            }

        return field_stats

    def _get_field_value(self, study: dict, field_type: str) -> Any:
        """Extract field value from study data."""
        if field_type in ["n", "events"]:
            arms = study.get("arms", [])
            if arms:
                return arms[0].get(field_type)
        elif field_type in ["estimate", "ci_low", "ci_high"]:
            outcomes = study.get("outcomes", [])
            if outcomes:
                return outcomes[0].get("effect", {}).get(field_type)
        return study.get(field_type)
