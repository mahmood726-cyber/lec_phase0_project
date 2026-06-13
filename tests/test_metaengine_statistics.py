"""Smoke tests for the meta-analysis statistics engine.

Locks in two correctness properties exercised by the portfolio sweep:
- HKSJ adjustment never narrows the interval below the standard RE CI
  (the q-statistic floor of max(1, q)).
- multivariate_pooling_check / multivariate_sensitivity_analysis are wired
  and return the active "Simple Average with Correlation Adjustment" method.
"""
import math

from lec.metaengine.statistics import (
    calculate_meta_analysis_hksj,
    multivariate_pooling_check,
    multivariate_sensitivity_analysis,
)


def _log_width(d):
    return math.log(d["ci_high"]) - math.log(d["ci_low"])


def test_basic_pooling_runs():
    studies = [
        {"estimate": 0.80, "se": 0.10, "study_id": "a"},
        {"estimate": 0.90, "se": 0.12, "study_id": "b"},
        {"estimate": 0.85, "se": 0.11, "study_id": "c"},
    ]
    res = calculate_meta_analysis_hksj(studies)
    assert "error" not in res
    assert res["n_studies"] == 3
    assert 0 < res["pooled"]["ci_low"] < res["pooled"]["estimate"] < res["pooled"]["ci_high"]


def test_hksj_floor_not_anticonservative():
    # Near-homogeneous studies drive the HKSJ q-statistic below 1; with the
    # floor applied the HKSJ CI must not be narrower than the standard RE CI.
    studies = [
        {"estimate": 0.80, "se": 0.10, "study_id": "a"},
        {"estimate": 0.82, "se": 0.10, "study_id": "b"},
        {"estimate": 0.79, "se": 0.10, "study_id": "c"},
    ]
    res = calculate_meta_analysis_hksj(studies)
    assert "hksj_adjusted" in res
    assert _log_width(res["hksj_adjusted"]) >= _log_width(res["pooled"]) - 1e-9


def test_empty_input_returns_error():
    assert "error" in calculate_meta_analysis_hksj([])


def test_multivariate_pooling_active_definition():
    outcomes = [
        {"estimate": 0.80, "se": 0.10},
        {"estimate": 0.90, "se": 0.12},
    ]
    res = multivariate_pooling_check(outcomes)
    assert res["adjusted"] is True
    assert res["method"] == "Simple Average with Correlation Adjustment"

    sens = multivariate_sensitivity_analysis(outcomes)
    assert len(sens["sensitivity_results"]) == 5
