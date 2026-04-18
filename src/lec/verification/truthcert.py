"""TruthCert - Bronze level verification certificate.

TruthCert (Bronze) certifies traceability and reproducibility:
- Provenance checks for critical fields
- 4 MVP validators ran and results recorded
- Multi-agent disagreement surfaced (not hidden)

Per CLAUDE.md: wording is "certifies reproducibility and traceability" NOT "proves"
"""

from pathlib import Path
from typing import Any

from lec.core import (
    load_json, write_json, sha256_file, utc_now_iso, generate_run_id
)
from lec.validators import run_all_validators
from lec.provenance import ProvenanceValidator


class TruthCertGenerator:
    """Generates TruthCert Bronze certificates."""

    ASSURANCE_LEVEL = "bronze"

    # Decision thresholds
    PASS_THRESHOLD = 0  # No critical issues
    FLAG_THRESHOLD = 3  # Up to 3 non-critical issues

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.certificates_dir = self.output_dir / "certificates"
        self.audit_logs_dir = self.output_dir / "audit_logs"
        self.certificates_dir.mkdir(parents=True, exist_ok=True)
        self.audit_logs_dir.mkdir(parents=True, exist_ok=True)

    def verify(self, extraction_path: Path) -> dict:
        """Run full verification pipeline and generate certificate.

        Args:
            extraction_path: Path to extraction JSON file

        Returns:
            dict with decision, certificate_path, audit_path
        """
        run_id = generate_run_id()
        extraction_data = load_json(extraction_path)

        audit_log = {
            "run_id": run_id,
            "started_at": utc_now_iso(),
            "assurance_level": self.ASSURANCE_LEVEL,
            "extraction_source": str(extraction_path),
            "extraction_sha256": sha256_file(extraction_path),
            "steps": []
        }

        # Step 1: Run provenance validation
        provenance_result = self._run_provenance_check(extraction_data, audit_log)

        # Step 2: Run 4 MVP validators
        validation_result = self._run_validators(extraction_data, audit_log)

        # Step 3: Check disagreement summary (if present)
        disagreement_result = self._check_disagreements(extraction_data, audit_log)

        # Step 4: Make decision
        decision, reasons = self._make_decision(
            provenance_result,
            validation_result,
            disagreement_result
        )

        audit_log["completed_at"] = utc_now_iso()
        audit_log["decision"] = decision
        audit_log["decision_reasons"] = reasons

        # Write audit log
        audit_path = self.audit_logs_dir / f"audit_{run_id}.json"
        audit_sha = write_json(audit_path, audit_log)

        # Generate certificate
        certificate = self._generate_certificate(
            run_id, decision, reasons, extraction_path, audit_path, audit_sha
        )

        cert_path = self.certificates_dir / f"truthcert_{run_id}.json"
        cert_sha = write_json(cert_path, certificate)

        return {
            "decision": decision,
            "reasons": reasons,
            "certificate_path": str(cert_path),
            "certificate_sha256": cert_sha,
            "audit_path": str(audit_path),
            "audit_sha256": audit_sha
        }

    def _run_provenance_check(self, extraction_data: dict,
                               audit_log: dict) -> dict:
        """Run provenance validation."""
        step = {
            "step": "provenance_check",
            "started_at": utc_now_iso()
        }

        validator = ProvenanceValidator()
        result = validator.validate(extraction_data)

        step["completed_at"] = utc_now_iso()
        step["status"] = result["status"]
        step["issue_count"] = result["issue_count"]
        step["issues"] = result["issues"]

        audit_log["steps"].append(step)
        return result

    def _run_validators(self, extraction_data: dict,
                        audit_log: dict) -> dict:
        """Run all 4 MVP validators."""
        step = {
            "step": "mvp_validators",
            "started_at": utc_now_iso()
        }

        result = run_all_validators(extraction_data)

        step["completed_at"] = utc_now_iso()
        step["validators_run"] = result["validators_run"]
        step["summary"] = result["summary"]
        step["results"] = result["results"]

        audit_log["steps"].append(step)
        return result

    def _check_disagreements(self, extraction_data: dict,
                              audit_log: dict) -> dict:
        """Check for extraction disagreements."""
        step = {
            "step": "disagreement_check",
            "started_at": utc_now_iso()
        }

        # Look for disagreement data in extraction
        disagreements = extraction_data.get("disagreements", {})
        summary = disagreements.get("summary", {})

        critical_count = summary.get("critical_disagreements", 0)
        total_count = summary.get("disagreements", 0)

        result = {
            "status": "PASS" if critical_count == 0 else "FLAG",
            "critical_disagreements": critical_count,
            "total_disagreements": total_count
        }

        step["completed_at"] = utc_now_iso()
        step.update(result)

        audit_log["steps"].append(step)
        return result

    def _make_decision(self, provenance_result: dict,
                       validation_result: dict,
                       disagreement_result: dict) -> tuple[str, list[str]]:
        """Make PASS/FLAG/FAIL decision based on all checks.

        Decision Logic (Transparent):
        - FAIL: Any critical issue (provenance missing for critical field,
                validator failure, critical extraction disagreement)
        - FLAG: Non-critical issues present (warnings, minor disagreements)
        - PASS: All checks passed with no issues

        Returns detailed reasons for transparency.
        """
        reasons = []
        detailed_reasons = []

        # Count critical issues
        critical_issues = 0

        # Provenance failures are critical
        if provenance_result["status"] == "FAIL":
            critical_issues += provenance_result["issue_count"]
            reasons.append(f"provenance_failures: {provenance_result['issue_count']}")
            # Add detailed breakdown
            for issue in provenance_result.get("issues", [])[:3]:  # First 3 issues
                detailed_reasons.append(
                    f"  - {issue.get('study_id', 'unknown')}: {issue.get('message', 'Missing provenance')}"
                )
            if provenance_result["issue_count"] > 3:
                detailed_reasons.append(f"  - ...and {provenance_result['issue_count'] - 3} more")

        # Validator failures
        if validation_result["summary"]["failed"] > 0:
            critical_issues += validation_result["summary"]["failed"]
            failed_validators = [
                r["validator"] for r in validation_result.get("results", [])
                if r.get("status") == "FAIL"
            ]
            reasons.append(f"validator_failures: {failed_validators}")
            for v in failed_validators:
                detailed_reasons.append(f"  - Validator '{v}' FAILED")

        # Critical disagreements
        if disagreement_result["critical_disagreements"] > 0:
            critical_issues += disagreement_result["critical_disagreements"]
            reasons.append(f"critical_disagreements: {disagreement_result['critical_disagreements']}")
            detailed_reasons.append(
                f"  - {disagreement_result['critical_disagreements']} field(s) with agent disagreement"
            )

        # Count non-critical issues
        non_critical = (
            validation_result["summary"]["flagged"] +
            (disagreement_result["total_disagreements"] -
             disagreement_result["critical_disagreements"])
        )

        if non_critical > 0:
            flagged_validators = [
                r["validator"] for r in validation_result.get("results", [])
                if r.get("status") == "FLAG"
            ]
            if flagged_validators:
                reasons.append(f"validator_warnings: {flagged_validators}")
            if disagreement_result["total_disagreements"] > disagreement_result["critical_disagreements"]:
                reasons.append(f"minor_disagreements: {disagreement_result['total_disagreements'] - disagreement_result['critical_disagreements']}")

        # Make decision with clear explanation
        if critical_issues > 0:
            decision = "FAIL"
            detailed_reasons.insert(0, f"DECISION: FAIL - {critical_issues} critical issue(s) found")
            detailed_reasons.append("ACTION REQUIRED: Fix provenance/extraction issues before proceeding")
        elif non_critical > self.FLAG_THRESHOLD:
            decision = "FLAG"
            detailed_reasons.insert(0, f"DECISION: FLAG - {non_critical} non-critical issue(s)")
            detailed_reasons.append("REVIEW RECOMMENDED: Manual review of flagged items advised")
        elif non_critical > 0:
            decision = "FLAG"
            detailed_reasons.insert(0, f"DECISION: FLAG - {non_critical} minor issue(s)")
            detailed_reasons.append("PROCEED WITH CAUTION: Minor issues detected")
        else:
            decision = "PASS"
            reasons.append("all_checks_passed")
            detailed_reasons.insert(0, "DECISION: PASS - All verification checks passed")
            detailed_reasons.append("CERTIFIED: Extraction is traceable and reproducible")

        # Combine reasons with detailed explanations
        reasons.append("---DETAILS---")
        reasons.extend(detailed_reasons)

        return decision, reasons

    def _generate_certificate(self, run_id: str, decision: str,
                               reasons: list[str], extraction_path: Path,
                               audit_path: Path, audit_sha: str) -> dict:
        """Generate TruthCert certificate."""
        # Find validation results in reasons or audit steps if needed, 
        # but let's just add a summary scorecard
        scorecard = {
            "provenance": "CHECKED",
            "validators": "COMPLETE",
            "disagreements": "SURFACED"
        }

        return {
            "truthcert_version": "0.1.0",
            "assurance_level": self.ASSURANCE_LEVEL,
            "run_id": run_id,
            "generated_at": utc_now_iso(),
            "decision": decision,
            "decision_reasons": reasons,
            "scorecard": scorecard,
            "statement": (
                f"This TruthCert ({self.ASSURANCE_LEVEL}) certifies the reproducibility "
                "and traceability of the extraction inputs. It does NOT guarantee "
                "zero extraction error or completeness of the evidence universe."
            ),
            "extraction": {
                "path": str(extraction_path),
                "sha256": sha256_file(extraction_path)
            },
            "audit_log": {
                "path": str(audit_path),
                "sha256": audit_sha
            },
            "validators_run": [
                "effect_direction",
                "inconsistent_n",
                "units_timepoint",
                "duplicates"
            ],
            "provenance_checked": True,
            "disagreements_surfaced": True
        }
