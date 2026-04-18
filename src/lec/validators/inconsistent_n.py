"""Inconsistent N Validator.

Validates consistency of sample sizes and events:
- N treatment + N control should approximately equal N total
- Events should not exceed N in each arm
- Checks for arithmetic inconsistencies
"""

from lec.validators.base import BaseValidator


class InconsistentNValidator(BaseValidator):
    """Validates sample size and event count consistency."""

    name = "inconsistent_n"
    description = "Validates N and events consistency across arms"

    # Tolerance for N total vs sum of arms (allows for missing data)
    N_TOLERANCE_RATIO = 0.05  # 5% tolerance

    def validate(self, extraction_data: dict) -> dict:
        """Validate N consistency for all studies."""
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
        """Validate single study's N consistency."""
        issues = []
        study_id = study.get("study_id", "unknown")

        # Check arm-level N consistency
        arms = study.get("arms", [])
        n_total_reported = study.get("n_total")
        n_sum = sum(arm.get("n", 0) for arm in arms if arm.get("n"))

        if n_total_reported and n_sum:
            diff = abs(n_total_reported - n_sum)
            tolerance = n_total_reported * self.N_TOLERANCE_RATIO

            if diff > tolerance:
                issues.append(self._make_issue(
                    study_id,
                    "n_total",
                    f"N total ({n_total_reported}) differs from sum of arms ({n_sum}) "
                    f"by {diff} (>{tolerance:.0f} tolerance)",
                    severity="warning",
                    details={
                        "n_total_reported": n_total_reported,
                        "n_sum_arms": n_sum,
                        "difference": diff
                    }
                ))

        # Check each arm
        for arm in arms:
            arm_issues = self._validate_arm(study_id, arm)
            issues.extend(arm_issues)

        # Check outcome-level consistency
        outcomes = study.get("outcomes", [])
        for outcome in outcomes:
            outcome_issues = self._validate_outcome(study_id, outcome, arms)
            issues.extend(outcome_issues)

        return issues

    def _validate_arm(self, study_id: str, arm: dict) -> list[dict]:
        """Validate single arm's N/events consistency."""
        issues = []
        arm_label = arm.get("label", "unknown_arm")
        n = arm.get("n")
        events = arm.get("events")

        if n is not None and events is not None:
            if events > n:
                issues.append(self._make_issue(
                    study_id,
                    f"arm.{arm_label}.events",
                    f"Events ({events}) exceeds N ({n}) in arm '{arm_label}'",
                    severity="error",
                    details={"arm": arm_label, "n": n, "events": events}
                ))

            if events == 0:
                issues.append(self._make_issue(
                    study_id,
                    f"arm.{arm_label}.events",
                    f"Zero events reported in arm '{arm_label}'. May cause calculation issues.",
                    severity="info",
                    details={"arm": arm_label, "events": 0}
                ))

            if events < 0:
                issues.append(self._make_issue(
                    study_id,
                    f"arm.{arm_label}.events",
                    f"Negative events ({events}) in arm '{arm_label}'",
                    severity="error",
                    details={"arm": arm_label, "events": events}
                ))

        if n is not None:
            if n < 10:
                issues.append(self._make_issue(
                    study_id,
                    f"arm.{arm_label}.n",
                    f"Very small sample size (n={n}) in arm '{arm_label}'",
                    severity="warning",
                    details={"arm": arm_label, "n": n}
                ))
            if n < 0:
                issues.append(self._make_issue(
                    study_id,
                    f"arm.{arm_label}.n",
                    f"Negative N ({n}) in arm '{arm_label}'",
                    severity="error",
                    details={"arm": arm_label, "n": n}
                ))

        return issues

    def _validate_outcome(self, study_id: str, outcome: dict,
                          arms: list[dict]) -> list[dict]:
        """Validate outcome-level N/events against arm totals."""
        issues = []
        outcome_name = outcome.get("name", "unknown_outcome")

        # For binary outcomes, check if outcome events match arm events
        arm_data = outcome.get("arm_data", {})

        for arm_label, data in arm_data.items():
            n = data.get("n")
            events = data.get("events")

            if n is not None and events is not None:
                if events > n:
                    issues.append(self._make_issue(
                        study_id,
                        f"outcome.{outcome_name}.{arm_label}",
                        f"Events ({events}) > N ({n}) for outcome '{outcome_name}' "
                        f"in arm '{arm_label}'",
                        severity="error",
                        details={
                            "outcome": outcome_name,
                            "arm": arm_label,
                            "n": n,
                            "events": events
                        }
                    ))

        return issues
