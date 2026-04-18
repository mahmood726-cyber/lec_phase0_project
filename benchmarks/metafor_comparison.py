#!/usr/bin/env python3
"""Benchmark LEC meta-analysis against R metafor package.

Generates comparison data and R code for validation.
Run the R code separately to verify numerical equivalence.

Reference: Viechtbauer W. metafor: Meta-Analysis Package for R.
           J Stat Softw 2010;36(3):1-48.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lec.core import load_json, write_json
from lec.metaengine.statistics import (
    calculate_meta_analysis_hksj,
    eggers_test,
    peters_test,
    trim_and_fill,
    estimate_se_asymmetric
)
import math


def generate_metafor_comparison():
    """Generate benchmark data for metafor comparison."""
    project_dir = Path(__file__).parent.parent
    data_dir = project_dir / "data"
    output_dir = project_dir / "benchmarks" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("LEC vs R metafor Benchmark Comparison")
    print("=" * 70)

    # Load extended extraction
    extraction_path = data_dir / "extended_extraction.json"
    extraction_data = load_json(extraction_path)

    # Prepare studies for meta-analysis (HR studies only for clean comparison)
    studies = []
    for study in extraction_data.get("studies", []):
        outcomes = study.get("outcomes", [])
        if outcomes:
            effect = outcomes[0].get("effect", {})
            measure = effect.get("measure", "")

            # Only include HR studies for benchmark
            if measure == "HR" and effect.get("estimate"):
                est = effect.get("estimate")
                ci_low = effect.get("ci_low")
                ci_high = effect.get("ci_high")

                # Calculate SE
                se = estimate_se_asymmetric(est, ci_low, ci_high)

                studies.append({
                    "study_id": study.get("study_id"),
                    "yi": round(math.log(est), 6),  # Log effect
                    "sei": round(se, 6),
                    "estimate": est,
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                    "se": se,
                    "n": study.get("n_total", 0)
                })

    print(f"\nStudies included (HR only): {len(studies)}")

    # Run LEC meta-analysis
    print("\n--- LEC Results ---")
    lec_result = calculate_meta_analysis_hksj(studies, use_hksj=True)

    print(f"Pooled estimate: {lec_result['pooled']['estimate']}")
    print(f"95% CI: [{lec_result['pooled']['ci_low']}, {lec_result['pooled']['ci_high']}]")
    print(f"SE: {lec_result['pooled']['se']}")
    print(f"z-value: {lec_result['pooled']['z']}")
    print(f"p-value: {lec_result['pooled']['p_value']}")
    print(f"I2: {lec_result['heterogeneity']['i2']}%")
    print(f"tau2: {lec_result['heterogeneity']['tau2']}")
    print(f"Q: {lec_result['heterogeneity']['q']} (df={lec_result['heterogeneity']['df']})")

    if "hksj_adjusted" in lec_result:
        print(f"HKSJ CI: [{lec_result['hksj_adjusted']['ci_low']}, {lec_result['hksj_adjusted']['ci_high']}]")

    print(f"PI: [{lec_result['prediction_interval']['pi_low']}, {lec_result['prediction_interval']['pi_high']}]")

    # Export data for R
    r_data = {
        "studies": studies,
        "lec_results": {
            "pooled_log": round(math.log(lec_result['pooled']['estimate']), 6),
            "pooled_exp": lec_result['pooled']['estimate'],
            "ci_low": lec_result['pooled']['ci_low'],
            "ci_high": lec_result['pooled']['ci_high'],
            "se": lec_result['pooled']['se'],
            "i2": lec_result['heterogeneity']['i2'],
            "tau2": lec_result['heterogeneity']['tau2'],
            "q": lec_result['heterogeneity']['q'],
            "pi_low": lec_result['prediction_interval']['pi_low'],
            "pi_high": lec_result['prediction_interval']['pi_high'],
        }
    }

    # Save for R comparison
    write_json(output_dir / "metafor_benchmark_data.json", r_data)

    # Generate R validation script
    r_script = generate_r_script(studies, lec_result)

    with open(output_dir / "validate_with_metafor.R", "w") as f:
        f.write(r_script)

    print(f"\n--- Output Files ---")
    print(f"Data: {output_dir / 'metafor_benchmark_data.json'}")
    print(f"R script: {output_dir / 'validate_with_metafor.R'}")

    # Calculate expected differences
    print("\n--- Expected Tolerances ---")
    print("Pooled estimate: +/- 0.01 (exp scale)")
    print("SE: +/- 0.005")
    print("I2: +/- 1%")
    print("tau2: +/- 0.001")
    print("Note: Small differences expected due to numerical precision")

    return r_data


def generate_r_script(studies: list, lec_result: dict) -> str:
    """Generate R script for metafor validation."""

    study_data = "\n".join([
        f'  c(yi = {s["yi"]}, sei = {s["sei"]}, study = "{s["study_id"]}"),'
        for s in studies
    ])

    return f'''# Validate LEC meta-analysis against R metafor
# Run this script in R to verify numerical equivalence

library(metafor)

# Study data from LEC extraction
data <- data.frame(
  study = c({", ".join([f'"{s["study_id"]}"' for s in studies])}),
  yi = c({", ".join([str(s["yi"]) for s in studies])}),
  sei = c({", ".join([str(s["sei"]) for s in studies])})
)

cat("\\n=== R metafor Results ===\\n")

# Random-effects meta-analysis (REML)
res <- rma(yi = yi, sei = sei, data = data, method = "REML")
print(res)

# Prediction interval
pred <- predict(res, transf = exp)
cat("\\nPrediction interval (exp scale):\\n")
print(pred)

# Forest plot
forest(res, transf = exp, header = TRUE,
       xlab = "Hazard Ratio", refline = 1)

# HKSJ adjustment
res_hksj <- rma(yi = yi, sei = sei, data = data, method = "REML", test = "knha")
cat("\\n=== HKSJ-adjusted Results ===\\n")
print(res_hksj)

# LEC comparison values
cat("\\n=== LEC Results for Comparison ===\\n")
cat("Pooled (log scale):", {round(math.log(lec_result["pooled"]["estimate"]), 6)}, "\\n")
cat("Pooled (exp scale):", {lec_result["pooled"]["estimate"]}, "\\n")
cat("CI low:", {lec_result["pooled"]["ci_low"]}, "\\n")
cat("CI high:", {lec_result["pooled"]["ci_high"]}, "\\n")
cat("SE:", {lec_result["pooled"]["se"]}, "\\n")
cat("I2:", {lec_result["heterogeneity"]["i2"]}, "%\\n")
cat("tau2:", {lec_result["heterogeneity"]["tau2"]}, "\\n")
cat("Q:", {lec_result["heterogeneity"]["q"]}, "\\n")

# Tolerance check
tol <- 0.02
lec_pooled <- {lec_result["pooled"]["estimate"]}
metafor_pooled <- exp(res$beta)

if (abs(lec_pooled - metafor_pooled) < tol) {{
  cat("\\n[PASS] Pooled estimates match within tolerance\\n")
}} else {{
  cat("\\n[WARN] Pooled estimates differ by:", abs(lec_pooled - metafor_pooled), "\\n")
}}

# Egger's test
cat("\\n=== Publication Bias Tests ===\\n")
regtest(res)

# Trim and fill
tf <- trimfill(res)
cat("\\nTrim and fill:\\n")
print(tf)
funnel(tf)

cat("\\n=== Benchmark Complete ===\\n")
'''


if __name__ == "__main__":
    generate_metafor_comparison()
