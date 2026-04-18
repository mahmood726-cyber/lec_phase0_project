"""Effect Direction Validator.

Validates that effect direction is consistent with:
- Reported effect estimates (OR/RR < 1 vs > 1)
- Arm labels (treatment vs control)
- Outcome direction cues in text
"""

from lec.validators.base import BaseValidator


class EffectDirectionValidator(BaseValidator):
    """Validates effect direction consistency."""

    name = "effect_direction"
    description = "Validates effect direction consistency across fields"

    # Keywords suggesting benefit (lower = better)
    BENEFIT_LOWER_KEYWORDS = [
        "mortality", "death", "adverse", "complication", "failure",
        "hospitalization", "recurrence", "relapse", "infection"
    ]

    # Keywords suggesting benefit (higher = better)
    BENEFIT_HIGHER_KEYWORDS = [
        "survival", "response", "remission", "cure", "success",
        "improvement", "quality of life"
    ]

    def validate(self, extraction_data: dict) -> dict:
        """Validate effect direction for all studies."""
        issues = []
        studies = extraction_data.get("studies", [])

        for study in studies:
            study_id = study.get("study_id", "unknown")
            study_issues = self._validate_study(study)
            issues.extend(study_issues)

        # Determine overall status
        if any(i["severity"] == "error" for i in issues):
            status = "FAIL"
        elif issues:
            status = "FLAG"
        else:
            status = "PASS"

        return self._make_result(status, issues)

    def _validate_study(self, study: dict) -> list[dict]:
        """Validate single study's effect direction."""
        issues = []
        study_id = study.get("study_id", "unknown")

        outcomes = study.get("outcomes", [])
        for outcome in outcomes:
            outcome_issues = self._validate_outcome(study_id, outcome)
            issues.extend(outcome_issues)

        return issues

    def _validate_outcome(self, study_id: str, outcome: dict) -> list[dict]:
        """Validate effect direction for single outcome."""
        issues = []

        effect = outcome.get("effect", {})
        estimate = effect.get("estimate")
        effect_direction = outcome.get("effect_direction")
        outcome_name = outcome.get("name", "").lower()

        if estimate is None:
            return issues  # Can't validate without estimate

        # 1. Extreme value check
        if estimate < 0.05 or estimate > 20:
             issues.append(self._make_issue(
                study_id,
                "effect_estimate",
                f"Extreme effect estimate: {estimate}. Verify extraction accuracy.",
                severity="warning",
                details={"estimate": estimate}
            ))

        # 2. Infer expected direction from outcome name
        inferred_direction = self._infer_direction(outcome_name)

        # 3. Check for ratio measures (OR, RR, HR)
        measure = effect.get("measure", "").upper()
        if measure in ["OR", "RR", "HR"]:
            estimate_favors = "treatment" if estimate < 1 else "control"

            # Cross-check with explicit direction if provided
            if effect_direction:
                if effect_direction != estimate_favors:
                    issues.append(self._make_issue(
                        study_id,
                        "effect_direction",
                        f"Direction mismatch: estimate {estimate} ({measure}) suggests "
                        f"'{estimate_favors}' but direction marked as '{effect_direction}'",
                        severity="error",
                        details={
                            "estimate": estimate,
                            "measure": measure,
                            "stated_direction": effect_direction,
                            "inferred_direction": estimate_favors
                        }
                    ))

            # Check against outcome type
            if inferred_direction and estimate < 1:
                if inferred_direction == "higher_is_better":
                    issues.append(self._make_issue(
                        study_id,
                        "effect_direction",
                        f"Potential direction inconsistency: '{outcome_name}' suggests "
                        f"higher is better, but {measure}={estimate} favors treatment",
                        severity="warning",
                        details={"outcome_name": outcome_name, "estimate": estimate}
                    ))
                elif inferred_direction == "lower_is_better":
                    # This is consistent (estimate < 1 favors treatment for bad outcome)
                    pass

        return issues

    def _infer_direction(self, outcome_name: str) -> str | None:
        """Infer expected effect direction from outcome name."""
        name_lower = outcome_name.lower()

        # Handle simple negations
        is_negated = any(neg in name_lower for neg in ["no ", "free from ", "without "])

        direction = None
        for keyword in self.BENEFIT_LOWER_KEYWORDS:
            if keyword in name_lower:
                direction = "lower_is_better"
                break

        if not direction:
            for keyword in self.BENEFIT_HIGHER_KEYWORDS:
                if keyword in name_lower:
                    direction = "higher_is_better"
                    break

        if direction and is_negated:
            # Flip direction if negated
            return "higher_is_better" if direction == "lower_is_better" else "lower_is_better"

        return direction
