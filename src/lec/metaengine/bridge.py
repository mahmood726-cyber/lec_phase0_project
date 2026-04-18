"""MetaEngine Bridge - Prepares input and parses output from MetaEngine.

The MetaEngine runs via a versioned JSON contract:
- Prepares metaengine_input.json from verified extraction
- Runs external JS/WASM MetaEngine (not implemented in Python)
- Parses metaengine_output.json back into LEC analysis results
"""

from pathlib import Path
from typing import Any
import math

from lec.core import load_json, write_json, sha256_file, utc_now_iso, get_logger

logger = get_logger("metaengine.bridge")


class MetaEngineBridge:
    """Bridge between LEC pipeline and MetaEngine computation."""

    CONTRACT_VERSION = "0.1.0"

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def prepare_input(self, extraction_data: dict, topic: str) -> dict:
        """Prepare MetaEngine input JSON from verified extraction.

        Args:
            extraction_data: Verified extraction data
            topic: Topic identifier

        Returns:
            dict with input_path and sha256
        """
        studies = extraction_data.get("studies", [])

        # Convert to MetaEngine format
        me_studies = []
        for study in studies:
            me_study = self._convert_study(study)
            if me_study:
                me_studies.append(me_study)

        # Determine outcome type and effect measure from first study
        outcome_type = "binary"
        effect_measure = "OR"
        if me_studies:
            outcome_type = me_studies[0].get("outcome_type", "binary")
            effect_measure = me_studies[0].get("effect_measure", "OR")

        me_input = {
            "contract_version": self.CONTRACT_VERSION,
            "created_at": utc_now_iso(),
            "topic": topic,
            "analysis_config": {
                "outcome_type": outcome_type,
                "effect_measure": effect_measure,
                "model": "random_effects",
                "method": "REML",
                "confidence_level": 0.95
            },
            "studies": me_studies
        }

        input_path = self.output_dir / f"metaengine_input_{topic}.json"
        sha = write_json(input_path, me_input)

        return {
            "path": str(input_path),
            "sha256": sha
        }

    def _convert_study(self, study: dict) -> dict | None:
        """Convert extraction study to MetaEngine format."""
        outcomes = study.get("outcomes", [])
        if not outcomes:
            return None

        # Use first outcome (primary)
        outcome = outcomes[0]
        effect = outcome.get("effect", {})

        estimate = effect.get("estimate")
        ci_low = effect.get("ci_low")
        ci_high = effect.get("ci_high")

        if estimate is None:
            return None

        # Calculate SE from CI if possible
        se = None
        if ci_low is not None and ci_high is not None:
            # For log scale (OR, RR, HR): SE = (log(ci_high) - log(ci_low)) / 3.92
            if effect.get("measure") in ["OR", "RR", "HR"] and estimate > 0:
                try:
                    log_ci_range = math.log(ci_high) - math.log(ci_low)
                    se = log_ci_range / 3.92  # 1.96 * 2
                except (ValueError, ZeroDivisionError):
                    pass

        return {
            "study_id": study.get("study_id"),
            "label": study.get("title", study.get("study_id")),
            "outcome_type": outcome.get("type", "binary"),
            "effect_measure": effect.get("measure", "OR"),
            "estimate": estimate,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "se": se,
            "n_total": study.get("n_total"),
            "weight": None  # Calculated by MetaEngine
        }

    def parse_output(self, output_path: Path) -> dict:
        """Parse MetaEngine output JSON.

        Args:
            output_path: Path to metaengine_output.json

        Returns:
            Parsed analysis results for LEC object
        """
        output_data = load_json(output_path)

        # Extract pooled estimate with safety checks
        pooled = output_data.get("pooled", {})
        if not pooled:
            logger.warning(f"No 'pooled' estimate found in {output_path}")

        heterogeneity = output_data.get("heterogeneity", {})
        if "i2" not in heterogeneity:
             logger.warning(f"No heterogeneity data found in {output_path}")

        return {
            "pooled": {
                "estimate": pooled.get("estimate"),
                "ci_low": pooled.get("ci_low"),
                "ci_high": pooled.get("ci_high"),
                "p_value": pooled.get("p_value"),
                "z": pooled.get("z"),
                "se": pooled.get("se")
            },
            "heterogeneity": {
                "i2": heterogeneity.get("i2"),
                "tau2": heterogeneity.get("tau2"),
                "q": heterogeneity.get("q"),
                "df": heterogeneity.get("df"),
                "p_heterogeneity": heterogeneity.get("p_value")
            },
            "study_weights": output_data.get("study_weights", []),
            "forest_data": output_data.get("forest_data", []),
            "model_meta": output_data.get("model_meta", {})
        }

    def create_contract(self, input_info: dict, output_path: Path) -> dict:
        """Create MetaEngine contract for LEC object.

        Args:
            input_info: dict with path and sha256 of input
            output_path: Path to metaengine_output.json

        Returns:
            Contract dict for LEC object
        """
        return {
            "contract_version": self.CONTRACT_VERSION,
            "input": {
                "path": input_info["path"],
                "sha256": input_info["sha256"]
            },
            "output": {
                "path": str(output_path),
                "sha256": sha256_file(output_path)
            },
            "engine_meta": {
                "engine": "metaengine",
                "version": "1.0.0",
                "method": "random_effects_REML"
            }
        }


def run_simple_meta_analysis(studies: list[dict]) -> dict:
    """Run simple meta-analysis (for demo/testing without external engine).

    This is a simplified implementation for Phase 0 testing.
    Production should use the external MetaEngine.
    """
    if not studies:
        return {"error": "No studies provided"}

    # Collect log estimates and SEs for random effects model
    log_estimates = []
    variances = []
    weights = []

    for study in studies:
        est = study.get("estimate")
        se = study.get("se")

        if est is None or est <= 0:
            continue

        log_est = math.log(est)
        log_estimates.append(log_est)

        if se and se > 0:
            var = se ** 2
        else:
            # Approximate variance from CI
            ci_low = study.get("ci_low", est * 0.5)
            ci_high = study.get("ci_high", est * 2.0)
            if ci_low > 0 and ci_high > 0:
                log_ci_range = math.log(ci_high) - math.log(ci_low)
                var = (log_ci_range / 3.92) ** 2
            else:
                var = 0.1  # Default

        variances.append(var)
        weights.append(1.0 / var if var > 0 else 1.0)

    if not log_estimates:
        return {"error": "No valid estimates"}

    # Fixed effects pooled estimate
    total_weight = sum(weights)
    pooled_log = sum(w * e for w, e in zip(weights, log_estimates)) / total_weight
    pooled_var = 1.0 / total_weight
    pooled_se = math.sqrt(pooled_var)

    # Convert back from log scale
    pooled_estimate = math.exp(pooled_log)
    ci_low = math.exp(pooled_log - 1.96 * pooled_se)
    ci_high = math.exp(pooled_log + 1.96 * pooled_se)

    # Heterogeneity (Q statistic)
    q = sum(w * (e - pooled_log) ** 2 for w, e in zip(weights, log_estimates))
    df = len(log_estimates) - 1

    # I-squared
    i2 = max(0, (q - df) / q * 100) if q > 0 and df > 0 else 0

    # Tau-squared (DerSimonian-Laird)
    c = total_weight - sum(w ** 2 for w in weights) / total_weight
    tau2 = max(0, (q - df) / c) if c > 0 else 0

    return {
        "pooled": {
            "estimate": round(pooled_estimate, 4),
            "ci_low": round(ci_low, 4),
            "ci_high": round(ci_high, 4),
            "se": round(pooled_se, 4)
        },
        "heterogeneity": {
            "i2": round(i2, 2),
            "tau2": round(tau2, 4),
            "q": round(q, 4),
            "df": df
        },
        "n_studies": len(log_estimates)
    }
