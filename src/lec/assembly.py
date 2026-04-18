"""LEC Object Assembly - Builds final Living Evidence Composite objects."""

from pathlib import Path
from typing import Optional

from lec.core import (
    load_json, write_json, sha256_file, utc_now_iso,
    generate_run_id, ManifestWriter, load_schema, validate_json
)


class LECBuilder:
    """Builds LEC objects from verified components."""

    LEC_VERSION = "0.1.0"

    def __init__(self, topic: str):
        """Initialize LEC builder.

        Args:
            topic: Topic identifier (e.g., colchicine_mi)
        """
        self.topic = topic
        self.run_id = generate_run_id()
        self.manifest = ManifestWriter(self.run_id)

        # Component paths
        self.discovery_path: Optional[Path] = None
        self.extraction_path: Optional[Path] = None
        self.metaengine_input_path: Optional[Path] = None
        self.metaengine_output_path: Optional[Path] = None
        self.truthcert_path: Optional[Path] = None
        self.audit_log_path: Optional[Path] = None

        # Loaded data
        self.question: Optional[dict] = None
        self.analysis_results: Optional[dict] = None

    def set_question(self, title: str, population: str, intervention: str,
                     comparator: str, outcome: str,
                     timeframe: Optional[str] = None,
                     keywords: Optional[list[str]] = None) -> "LECBuilder":
        """Set the PICO question for the LEC object."""
        self.question = {
            "title": title,
            "pico": {
                "population": population,
                "intervention": intervention,
                "comparator": comparator,
                "outcome": outcome
            }
        }
        if timeframe:
            self.question["pico"]["timeframe"] = timeframe
        if keywords:
            self.question["keywords"] = keywords
        return self

    def add_discovery(self, path: Path) -> "LECBuilder":
        """Add discovery artifact."""
        self.discovery_path = Path(path)
        self.manifest.add_artifact("discovery", self.discovery_path)
        return self

    def add_extraction(self, path: Path) -> "LECBuilder":
        """Add extraction artifact."""
        self.extraction_path = Path(path)
        self.manifest.add_artifact("extraction", self.extraction_path)
        return self

    def add_metaengine(self, input_path: Path = None,
                       output_path: Path = None) -> "LECBuilder":
        """Add MetaEngine artifacts."""
        if input_path:
            self.metaengine_input_path = Path(input_path)
            self.manifest.add_artifact("metaengine_input", self.metaengine_input_path)
        if output_path:
            self.metaengine_output_path = Path(output_path)
            self.manifest.add_artifact("metaengine_output", self.metaengine_output_path)
        return self

    def add_truthcert(self, cert_path: Path,
                      audit_path: Optional[Path] = None) -> "LECBuilder":
        """Add TruthCert artifacts."""
        self.truthcert_path = Path(cert_path)
        self.manifest.add_artifact("truthcert", self.truthcert_path)
        if audit_path:
            self.audit_log_path = Path(audit_path)
            self.manifest.add_artifact("audit_log", self.audit_log_path)
        return self

    def set_analysis_results(self, results: dict) -> "LECBuilder":
        """Set analysis results (pooled estimate, heterogeneity)."""
        self.analysis_results = results
        return self

    def build(self, output_path: Path, schema_path: Optional[Path] = None) -> Path:
        """Build and write the LEC object.

        Args:
            output_path: Path to write LEC JSON
            schema_path: Optional path to LEC schema for validation

        Returns:
            Path to written LEC object
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Load TruthCert data
        truthcert_data = {}
        if self.truthcert_path and self.truthcert_path.exists():
            truthcert_data = load_json(self.truthcert_path)

        # Load extraction for analysis data
        extraction_data = {}
        if self.extraction_path and self.extraction_path.exists():
            extraction_data = load_json(self.extraction_path)

        # Determine analysis parameters from extraction
        outcome_type = "binary"
        effect_measure = "OR"
        studies = extraction_data.get("studies", [])
        if studies:
            outcomes = studies[0].get("outcomes", [])
            if outcomes:
                outcome_type = outcomes[0].get("type", "binary")
                effect = outcomes[0].get("effect", {})
                effect_measure = effect.get("measure", "OR")

        # Build LEC object
        lec_object = {
            "lec_version": self.LEC_VERSION,
            "created_at_utc": utc_now_iso(),
            "updated_at_utc": utc_now_iso(),
            "question": self.question or self._default_question(),
            "evidence_universe": self._build_evidence_universe(),
            "included_studies": self._build_included_studies(extraction_data),
            "analysis": self._build_analysis(outcome_type, effect_measure),
            "verification": self._build_verification(truthcert_data),
            "reproducibility": self._build_reproducibility(output_path)
        }

        # Validate against schema if provided
        if schema_path:
            schema = load_schema(schema_path)
            is_valid, errors = validate_json(lec_object, schema)
            if not is_valid:
                raise ValueError(f"LEC object validation failed: {errors}")

        # Write LEC object
        write_json(output_path, lec_object)

        # Write manifest
        manifest_path = output_path.parent / f"manifest_{self.run_id}.json"
        self.manifest.write(manifest_path)

        return output_path

    def _default_question(self) -> dict:
        """Create default question from topic."""
        return {
            "title": f"Meta-analysis for topic: {self.topic}",
            "pico": {
                "population": "To be specified",
                "intervention": "To be specified",
                "comparator": "To be specified",
                "outcome": "To be specified"
            }
        }

    def _build_evidence_universe(self) -> dict:
        """Build evidence universe section with PRISMA tracking."""
        universe = {
            "discovery_artifacts": [],
            "prisma_flow": {
                "identified": 0,
                "screened": 0,
                "excluded": 0,
                "included": 0
            }
        }

        if self.discovery_path and self.discovery_path.exists():
            discovery_data = load_json(self.discovery_path)
            universe["discovery_artifacts"].append({
                "path": str(self.discovery_path),
                "sha256": sha256_file(self.discovery_path),
                "candidate_count": discovery_data.get("candidate_count",
                    len(discovery_data.get("discovered_trials", [])))
            })
            universe["statistics"] = discovery_data.get("statistics",
                discovery_data.get("disposition_summary", {}))
            
            # Aggregate PRISMA data
            prisma = discovery_data.get("prisma", {})
            for key in universe["prisma_flow"]:
                universe["prisma_flow"][key] += prisma.get(key, 0)

        return universe

    def _build_included_studies(self, extraction_data: dict) -> dict:
        """Build included studies section."""
        studies = extraction_data.get("studies", [])
        return {
            "count": len(studies),
            "study_ids": [s.get("study_id") for s in studies]
        }

    def _build_analysis(self, outcome_type: str, effect_measure: str) -> dict:
        """Build analysis section."""
        # Use provided results or defaults
        results = self.analysis_results or {
            "pooled": {"estimate": None, "ci_low": None, "ci_high": None},
            "heterogeneity": {"i2": None, "tau2": None}
        }

        analysis = {
            "outcome_type": outcome_type,
            "effect_measure": effect_measure,
            "model": {
                "type": "random_effects",
                "method": "REML"
            },
            "results": {
                "pooled": results.get("pooled", {}),
                "heterogeneity": results.get("heterogeneity", {})
            },
            "metaengine_contract": self._build_metaengine_contract()
        }

        return analysis

    def _build_metaengine_contract(self) -> dict:
        """Build MetaEngine contract section."""
        contract = {
            "contract_version": "0.1.0",
            "input": {"path": "", "sha256": ""},
            "output": {"path": "", "sha256": ""}
        }

        if self.metaengine_input_path and self.metaengine_input_path.exists():
            contract["input"] = {
                "path": str(self.metaengine_input_path),
                "sha256": sha256_file(self.metaengine_input_path)
            }

        if self.metaengine_output_path and self.metaengine_output_path.exists():
            contract["output"] = {
                "path": str(self.metaengine_output_path),
                "sha256": sha256_file(self.metaengine_output_path)
            }

        return contract

    def _build_verification(self, truthcert_data: dict) -> dict:
        """Build verification section."""
        verification = {
            "truthcert": {
                "assurance_level": truthcert_data.get("assurance_level", "bronze"),
                "decision": truthcert_data.get("decision", "PENDING"),
                "certificate": {"path": "", "sha256": ""},
                "audit_log": {"path": "", "sha256": ""}
            }
        }

        if self.truthcert_path and self.truthcert_path.exists():
            verification["truthcert"]["certificate"] = {
                "path": str(self.truthcert_path),
                "sha256": sha256_file(self.truthcert_path)
            }

        if self.audit_log_path and self.audit_log_path.exists():
            verification["truthcert"]["audit_log"] = {
                "path": str(self.audit_log_path),
                "sha256": sha256_file(self.audit_log_path)
            }

        return verification

    def _build_reproducibility(self, output_path: Path) -> dict:
        """Build reproducibility section."""
        manifest_path = output_path.parent / f"manifest_{self.run_id}.json"

        return {
            "run_id": self.run_id,
            "manifest": {
                "path": str(manifest_path),
                "sha256": ""  # Will be computed after manifest is written
            },
            "artifacts": self.manifest.artifacts
        }
