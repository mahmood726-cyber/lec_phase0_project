"""Units and Timepoint Validator.

Validates:
- Units are specified and consistent for continuous outcomes
- Timepoints are specified and comparable across studies
- Effect measures match outcome types (OR for binary, MD for continuous)
"""

from lec.validators.base import BaseValidator


class UnitsTimepointValidator(BaseValidator):
    """Validates units and timepoint consistency."""

    name = "units_timepoint"
    description = "Validates units and timepoints are specified and consistent"

    # Binary outcome effect measures
    BINARY_MEASURES = ["OR", "RR", "HR", "ARD", "NNT"]

    # Continuous outcome effect measures
    CONTINUOUS_MEASURES = ["MD", "SMD", "WMD", "ROM"]

    # Common time units
    TIME_UNITS = ["days", "weeks", "months", "years", "hours"]

    def validate(self, extraction_data: dict) -> dict:
        """Validate units and timepoints for all studies."""
        issues = []
        studies = extraction_data.get("studies", [])

        # Collect all timepoints for cross-study comparison
        all_timepoints = []

        for study in studies:
            study_id = study.get("study_id", "unknown")
            study_issues, timepoints = self._validate_study(study)
            issues.extend(study_issues)
            all_timepoints.extend([(study_id, t) for t in timepoints])

        # Check for timepoint heterogeneity across studies
        heterogeneity_issues = self._check_timepoint_heterogeneity(all_timepoints)
        issues.extend(heterogeneity_issues)

        # Determine overall status
        if any(i["severity"] == "error" for i in issues):
            status = "FAIL"
        elif issues:
            status = "FLAG"
        else:
            status = "PASS"

        return self._make_result(status, issues)

    def _validate_study(self, study: dict) -> tuple[list[dict], list[dict]]:
        """Validate single study. Returns (issues, timepoints)."""
        issues = []
        timepoints = []
        study_id = study.get("study_id", "unknown")

        outcomes = study.get("outcomes", [])
        for outcome in outcomes:
            outcome_issues, tp = self._validate_outcome(study_id, outcome)
            issues.extend(outcome_issues)
            if tp:
                timepoints.append(tp)

        return issues, timepoints

    def _validate_outcome(self, study_id: str, outcome: dict) -> tuple[list[dict], dict | None]:
        """Validate single outcome. Returns (issues, timepoint_info)."""
        issues = []
        outcome_name = outcome.get("name", "unknown")
        outcome_type = outcome.get("type", "unknown")
        effect = outcome.get("effect", {})
        measure = effect.get("measure", "").upper()
        timepoint = outcome.get("timepoint")
        timepoint_unit = outcome.get("timepoint_unit")
        units = outcome.get("units")

        # Check measure matches outcome type
        if outcome_type == "binary":
            if measure and measure not in self.BINARY_MEASURES:
                issues.append(self._make_issue(
                    study_id,
                    f"outcome.{outcome_name}.measure",
                    f"Measure '{measure}' unusual for binary outcome (expected: {self.BINARY_MEASURES})",
                    severity="warning",
                    details={"measure": measure, "outcome_type": outcome_type}
                ))
        elif outcome_type == "continuous":
            if measure and measure not in self.CONTINUOUS_MEASURES:
                issues.append(self._make_issue(
                    study_id,
                    f"outcome.{outcome_name}.measure",
                    f"Measure '{measure}' unusual for continuous outcome (expected: {self.CONTINUOUS_MEASURES})",
                    severity="warning",
                    details={"measure": measure, "outcome_type": outcome_type}
                ))

            # Continuous outcomes should have units
            if not units:
                issues.append(self._make_issue(
                    study_id,
                    f"outcome.{outcome_name}.units",
                    f"Missing units for continuous outcome '{outcome_name}'",
                    severity="warning",
                    details={"outcome_name": outcome_name}
                ))

        # Check timepoint specification
        if not timepoint and not timepoint_unit:
            issues.append(self._make_issue(
                study_id,
                f"outcome.{outcome_name}.timepoint",
                f"Missing timepoint for outcome '{outcome_name}'",
                severity="warning",
                details={"outcome_name": outcome_name}
            ))

        timepoint_info = None
        if timepoint or timepoint_unit:
            timepoint_info = {
                "study_id": study_id,
                "outcome": outcome_name,
                "value": timepoint,
                "unit": timepoint_unit
            }

        return issues, timepoint_info

    def _check_timepoint_heterogeneity(self, all_timepoints: list[tuple]) -> list[dict]:
        """Check for heterogeneity in timepoints across studies."""
        issues = []

        if len(all_timepoints) < 2:
            return issues

        # Group by unit
        units = set()
        for study_id, tp in all_timepoints:
            if tp and tp.get("unit"):
                units.add(tp["unit"].lower())

        if len(units) > 1:
            issues.append(self._make_issue(
                "cross_study",
                "timepoint_units",
                f"Heterogeneous timepoint units across studies: {units}",
                severity="warning",
                details={"unique_units": list(units)}
            ))

        return issues
