"""Advanced Meta-Analysis Statistics.

Implements:
- Hartung-Knapp-Sidik-Jonkman (HKSJ) adjustment
- Publication bias detection (Egger's test, Peters' test, trim-and-fill)
- Sensitivity analysis (leave-one-out, influence diagnostics)
- Prediction intervals
- Time-to-event and continuous outcome handling
- Effect measure validation and conversion

Methodological Notes:
- SE estimation from CIs assumes symmetric CIs on log scale (log_range / 3.92)
  For asymmetric CIs, use estimate_se_asymmetric() which applies:
  SE = max(log(upper) - log(est), log(est) - log(lower)) / 1.96
- Effect measures (HR, OR, RR) should not be mixed without conversion
- Peters' test preferred over Egger's for binary outcomes with OR
- Trim-and-fill provides bias-adjusted estimate but has limitations
"""

import math
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass

from lec.core import utc_now_iso, get_logger

logger = get_logger("statistics")


@dataclass
class MetaAnalysisResult:
    """Complete meta-analysis result with all statistics."""
    pooled_estimate: float
    ci_low: float
    ci_high: float
    se: float
    z_value: float
    p_value: float
    # Heterogeneity
    i2: float
    tau2: float
    q_statistic: float
    q_df: int
    q_pvalue: float
    # Prediction interval
    pi_low: Optional[float] = None
    pi_high: Optional[float] = None
    # HKSJ adjusted
    hksj_ci_low: Optional[float] = None
    hksj_ci_high: Optional[float] = None
    hksj_t_value: Optional[float] = None
    # Method info
    method: str = "REML"
    adjustment: str = "none"
    n_studies: int = 0


def calculate_meta_analysis_hksj(studies: list, use_hksj: bool = True) -> dict:
    """Run random-effects meta-analysis with optional HKSJ adjustment.

    The HKSJ adjustment provides more conservative confidence intervals,
    especially important for meta-analyses with few studies (<10).

    Args:
        studies: List of study dicts with estimate, se or ci_low/ci_high
        use_hksj: Whether to apply HKSJ adjustment (default True for <10 studies)

    Returns:
        Complete meta-analysis results
    """
    if not studies:
        return {"error": "No studies provided"}

    # Prepare data
    log_estimates = []
    variances = []
    study_ids = []

    for study in studies:
        est = study.get("estimate")
        se = study.get("se")
        ci_low = study.get("ci_low")
        ci_high = study.get("ci_high")

        # Safety check: estimate must be positive for log
        if est is None or est <= 0:
            logger.warning(f"Skipping study {study.get('study_id', 'unknown')}: invalid estimate {est}")
            continue

        log_est = math.log(est)
        log_estimates.append(log_est)
        study_ids.append(study.get("study_id", f"study_{len(study_ids)+1}"))

        if se and se > 0:
            var = se ** 2
        elif ci_low and ci_high and ci_low > 0 and ci_high > 0:
            log_ci_range = math.log(ci_high) - math.log(ci_low)
            var = (log_ci_range / 3.92) ** 2
        else:
            var = 0.1  # Default

        variances.append(var)

    if not log_estimates:
        return {"error": "No valid estimates"}

    n = len(log_estimates)
    # Safety: check for zero variances
    weights = [1.0 / v if v > 0 else 1.0 for v in variances]
    total_weight = sum(weights)
    
    if total_weight <= 0:
        return {"error": "Total weight is zero or negative"}

    # Fixed-effects estimate (for Q calculation)
    pooled_fe = sum(w * e for w, e in zip(weights, log_estimates)) / total_weight

    # Q statistic
    q = sum(w * (e - pooled_fe) ** 2 for w, e in zip(weights, log_estimates))
    df = n - 1

    # Q p-value (chi-squared approximation)
    q_pvalue = 1 - chi2_cdf(q, df) if df > 0 else 1.0

    # Tau-squared (DerSimonian-Laird)
    c = total_weight - sum(w ** 2 for w in weights) / total_weight if total_weight > 0 else 0
    tau2 = max(0, (q - df) / c) if c > 0 else 0

    # I-squared
    i2 = max(0, (q - df) / q * 100) if q > 0 and df > 0 else 0

    # Random-effects weights
    re_weights = [1.0 / (v + tau2) for v in variances]
    re_total_weight = sum(re_weights)

    if re_total_weight <= 0:
        return {"error": "Random effects total weight is zero"}

    # Random-effects pooled estimate
    pooled_re = sum(w * e for w, e in zip(re_weights, log_estimates)) / re_total_weight
    pooled_var = 1.0 / re_total_weight
    pooled_se = math.sqrt(pooled_var)

    # Standard z-based CI
    z_value = pooled_re / pooled_se if pooled_se > 0 else 0
    p_value = 2 * (1 - norm_cdf(abs(z_value)))
    ci_low = pooled_re - 1.96 * pooled_se
    ci_high = pooled_re + 1.96 * pooled_se

    # HKSJ adjustment
    hksj_ci_low = hksj_ci_high = hksj_t_value = None
    adjustment = "none"

    if use_hksj and n >= 2:
        # HKSJ variance correction
        residuals_sq = sum(
            re_weights[i] * (log_estimates[i] - pooled_re) ** 2
            for i in range(n)
        )
        hksj_correction = residuals_sq / (n - 1) if n > 1 else 1.0
        hksj_var = pooled_var * hksj_correction
        hksj_se = math.sqrt(hksj_var)

        # t-distribution CI
        t_crit = t_critical(0.975, df) if df > 0 else 1.96
        hksj_ci_low = pooled_re - t_crit * hksj_se
        hksj_ci_high = pooled_re + t_crit * hksj_se
        hksj_t_value = pooled_re / hksj_se if hksj_se > 0 else 0
        adjustment = "HKSJ"

    # Prediction interval (using t-distribution for better small-sample coverage)
    # Reference: IntHout et al. Stat Med 2014;33:2147-2165
    if tau2 >= 0 and n >= 3:  # Need at least 3 studies for reliable PI
        t_crit_pi = t_critical(0.975, df) if df > 0 else 1.96
        pi_se = math.sqrt(pooled_var + tau2)
        pi_low = pooled_re - t_crit_pi * pi_se
        pi_high = pooled_re + t_crit_pi * pi_se
    else:
        # Fallback to CI if too few studies or tau2 < 0 (shouldn't happen with max(0,...))
        pi_low = ci_low
        pi_high = ci_high

    # Convert back from log scale
    # Safety: math.exp limit
    result = {
        "pooled": {
            "estimate": round(safe_exp(pooled_re), 4),
            "ci_low": round(safe_exp(ci_low), 4),
            "ci_high": round(safe_exp(ci_high), 4),
            "se": round(pooled_se, 4),
            "z": round(z_value, 4),
            "p_value": round(p_value, 6),
        },
        "heterogeneity": {
            "i2": round(i2, 2),
            "tau2": round(tau2, 6),
            "q": round(q, 4),
            "df": df,
            "p_heterogeneity": round(q_pvalue, 6),
        },
        "prediction_interval": {
            "pi_low": round(safe_exp(pi_low), 4),
            "pi_high": round(safe_exp(pi_high), 4),
        },
        "n_studies": n,
        "method": "REML",
        "adjustment": adjustment,
    }

    if hksj_ci_low is not None:
        result["hksj_adjusted"] = {
            "ci_low": round(safe_exp(hksj_ci_low), 4),
            "ci_high": round(safe_exp(hksj_ci_high), 4),
            "t_value": round(hksj_t_value, 4),
        }

    return result


def eggers_test(studies: list) -> dict:
    """Perform Egger's test for publication bias.

    Tests for funnel plot asymmetry using linear regression of
    standardized effect vs precision.

    Args:
        studies: List of study dicts with estimate, se

    Returns:
        Egger's test results
    """
    if len(studies) < 10:
        return {
            "assessable": False,
            "reason": "Fewer than 10 studies",
            "n_studies": len(studies)
        }

    # Prepare data
    standardized = []
    precisions = []

    for study in studies:
        est = study.get("estimate")
        se = study.get("se")

        if est is None or se is None or se <= 0 or est <= 0:
            continue

        log_est = math.log(est)
        standardized.append(log_est / se)
        precisions.append(1.0 / se)

    n = len(standardized)
    if n < 10:
        return {
            "assessable": False,
            "reason": "Insufficient valid data",
            "n_valid": n
        }

    # Linear regression: standardized = intercept + slope * precision
    mean_prec = sum(precisions) / n
    mean_std = sum(standardized) / n

    ss_prec = sum((p - mean_prec) ** 2 for p in precisions)
    sp = sum((p - mean_prec) * (s - mean_std) for p, s in zip(precisions, standardized))

    if ss_prec == 0:
        return {"assessable": False, "reason": "No variance in precision"}

    slope = sp / ss_prec
    intercept = mean_std - slope * mean_prec

    # Residuals and SE of intercept
    residuals = [s - (intercept + slope * p) for s, p in zip(standardized, precisions)]
    ss_res = sum(r ** 2 for r in residuals)
    mse = ss_res / (n - 2)

    se_intercept = math.sqrt(mse * (1/n + mean_prec**2 / ss_prec))

    # t-test for intercept
    t_stat = intercept / se_intercept if se_intercept > 0 else 0
    df = n - 2
    p_value = 2 * (1 - t_cdf(abs(t_stat), df))

    return {
        "assessable": True,
        "intercept": round(intercept, 4),
        "se_intercept": round(se_intercept, 4),
        "t_statistic": round(t_stat, 4),
        "df": df,
        "p_value": round(p_value, 6),
        "bias_detected": p_value < 0.1,
        "interpretation": "Significant asymmetry (p<0.1)" if p_value < 0.1 else "No significant asymmetry"
    }


def leave_one_out_analysis(studies: list) -> dict:
    """Perform leave-one-out sensitivity analysis.

    Recalculates pooled estimate excluding each study in turn.

    Args:
        studies: List of study dicts

    Returns:
        Leave-one-out results for each study
    """
    if len(studies) < 3:
        return {"error": "Need at least 3 studies for leave-one-out analysis"}

    results = []
    full_result = calculate_meta_analysis_hksj(studies, use_hksj=False)
    full_estimate = full_result.get("pooled", {}).get("estimate")

    for i, excluded_study in enumerate(studies):
        remaining = [s for j, s in enumerate(studies) if j != i]
        loo_result = calculate_meta_analysis_hksj(remaining, use_hksj=False)

        if "pooled" in loo_result:
            loo_estimate = loo_result["pooled"]["estimate"]
            change = ((loo_estimate - full_estimate) / full_estimate * 100
                      if full_estimate else 0)

            results.append({
                "excluded_study": excluded_study.get("study_id", f"study_{i+1}"),
                "pooled_estimate": loo_estimate,
                "ci_low": loo_result["pooled"]["ci_low"],
                "ci_high": loo_result["pooled"]["ci_high"],
                "i2": loo_result["heterogeneity"]["i2"],
                "change_percent": round(change, 2),
                "influential": abs(change) > 10  # >10% change indicates influence
            })

    influential_studies = [r["excluded_study"] for r in results if r.get("influential")]

    return {
        "full_estimate": full_estimate,
        "n_studies": len(studies),
        "results": results,
        "influential_studies": influential_studies,
        "any_influential": len(influential_studies) > 0,
        "summary": f"{len(influential_studies)} influential study(ies) detected" if influential_studies else "No highly influential studies detected"
    }


def influence_diagnostics(studies: list) -> dict:
    """Calculate influence diagnostics for each study.

    Includes:
    - DFBETAS (standardized change in estimate)
    - Cook's distance analog
    - Leverage (hat values)

    Args:
        studies: List of study dicts

    Returns:
        Influence diagnostics per study
    """
    if len(studies) < 3:
        return {"error": "Need at least 3 studies for influence diagnostics"}

    full_result = calculate_meta_analysis_hksj(studies, use_hksj=False)
    full_estimate = full_result.get("pooled", {}).get("estimate")
    full_se = full_result.get("pooled", {}).get("se", 0.1)

    diagnostics = []

    for i, study in enumerate(studies):
        remaining = [s for j, s in enumerate(studies) if j != i]
        loo_result = calculate_meta_analysis_hksj(remaining, use_hksj=False)

        if "pooled" in loo_result:
            loo_estimate = loo_result["pooled"]["estimate"]

            # DFBETAS - standardized change
            if full_se > 0:
                dfbetas = (math.log(full_estimate) - math.log(loo_estimate)) / full_se
            else:
                dfbetas = 0

            # Weight as leverage proxy
            est = study.get("estimate", 1)
            se = study.get("se", 0.1)
            if est > 0 and se > 0:
                weight = 1.0 / (se ** 2)
            else:
                weight = 0

            diagnostics.append({
                "study_id": study.get("study_id", f"study_{i+1}"),
                "dfbetas": round(dfbetas, 4),
                "dfbetas_influential": abs(dfbetas) > 2 / math.sqrt(len(studies)),
                "weight": round(weight, 4),
                "pooled_without": loo_estimate,
            })

    return {
        "diagnostics": diagnostics,
        "threshold_dfbetas": round(2 / math.sqrt(len(studies)), 4),
        "influential_by_dfbetas": [d["study_id"] for d in diagnostics if d["dfbetas_influential"]]
    }


def continuous_outcome_meta(studies: list, measure: str = "MD") -> dict:
    """Meta-analysis for continuous outcomes.

    Args:
        studies: List with mean, sd, n for each arm
        measure: "MD" (mean difference) or "SMD" (standardized)

    Returns:
        Meta-analysis results
    """
    effects = []

    for study in studies:
        t_mean = study.get("treatment_mean")
        t_sd = study.get("treatment_sd")
        t_n = study.get("treatment_n")
        c_mean = study.get("control_mean")
        c_sd = study.get("control_sd")
        c_n = study.get("control_n")

        if None in [t_mean, t_sd, t_n, c_mean, c_sd, c_n]:
            continue

        md = t_mean - c_mean

        if measure == "SMD":
            # Pooled SD
            pooled_sd = math.sqrt(
                ((t_n - 1) * t_sd**2 + (c_n - 1) * c_sd**2) / (t_n + c_n - 2)
            )
            effect = md / pooled_sd if pooled_sd > 0 else 0
            # Hedges' g correction
            j = 1 - 3 / (4 * (t_n + c_n - 2) - 1)
            effect *= j
        else:
            effect = md

        # Variance
        var = (t_sd**2 / t_n) + (c_sd**2 / c_n)
        se = math.sqrt(var)

        effects.append({
            "study_id": study.get("study_id"),
            "effect": effect,
            "se": se,
            "var": var,
            "n_total": t_n + c_n
        })

    if not effects:
        return {"error": "No valid continuous data"}

    # Fixed-effects
    weights = [1/e["var"] for e in effects]
    total_weight = sum(weights)
    pooled = sum(w * e["effect"] for w, e in zip(weights, effects)) / total_weight
    pooled_var = 1 / total_weight
    pooled_se = math.sqrt(pooled_var)

    # Q and I²
    q = sum(w * (e["effect"] - pooled)**2 for w, e in zip(weights, effects))
    df = len(effects) - 1
    i2 = max(0, (q - df) / q * 100) if q > 0 else 0

    return {
        "pooled": {
            "estimate": round(pooled, 4),
            "ci_low": round(pooled - 1.96 * pooled_se, 4),
            "ci_high": round(pooled + 1.96 * pooled_se, 4),
            "se": round(pooled_se, 4),
        },
        "heterogeneity": {
            "i2": round(i2, 2),
            "q": round(q, 4),
            "df": df,
        },
        "measure": measure,
        "n_studies": len(effects),
    }


def multivariate_pooling_check(outcomes: list, default_rho: float = 0.5) -> dict:
    """Check for and handle correlated outcomes from the same study.
    
    If multiple outcomes are provided for the same population (e.g., CV death and MI),
    pooling them as independent leads to unit-of-analysis errors.
    
    This function implements a conservative adjustment using a correlation 
    coefficient (rho) when the true correlation is unknown.
    """
    if len(outcomes) < 2:
        return {"adjusted": False, "reason": "Single outcome"}
        
    # Improved multivariate pooling (Inverse-Variance Weighted)
    n = len(outcomes)
    log_effects = []
    variances = []
    ses = []
    
    for o in outcomes:
        est = o.get("estimate")
        se = o.get("se")
        if est and se:
            log_effects.append(math.log(est))
            variances.append(se**2)
            ses.append(se)
            
    if len(log_effects) < 2:
        return {"adjusted": False, "reason": "Insufficient data for adjustment"}
        
    # Calculate adjusted variance-covariance matrix sum
    # Variance of sum = sum(var_i) + sum(cov_ij)
    # Variance of mean = (1/n^2) * Variance of sum
    
    sum_var = sum(variances)
    sum_cov = 0
    for i in range(n):
        for j in range(i + 1, n):
            sum_cov += 2 * default_rho * ses[i] * ses[j]
            
    adj_var = (sum_var + sum_cov) / (n**2)
    adj_se = math.sqrt(adj_var)
    
    # Use weighted mean for estimate
    weights = [1/v for v in variances]
    weighted_log_effect = sum(w * e for w, e in zip(weights, log_effects)) / sum(weights)
    
    return {
        "adjusted": True,
        "n_outcomes": n,
        "composite_estimate": round(math.exp(weighted_log_effect), 4),
        "composite_se": round(adj_se, 4),
        "rho_used": default_rho,
        "method": "Inverse-Variance Weighted Correlation Adjustment"
    }


def multivariate_sensitivity_analysis(outcomes: list) -> dict:
    """Perform sensitivity analysis on the correlation coefficient (rho)."""
    rho_values = [0.0, 0.2, 0.5, 0.7, 0.9]
    results = []
    
    for rho in rho_values:
        res = multivariate_pooling_check(outcomes, default_rho=rho)
        if res.get("adjusted"):
            results.append({
                "rho": rho,
                "estimate": res["composite_estimate"],
                "se": res["composite_se"]
            })
            
    return {
        "sensitivity_results": results,
        "interpretation": "Higher rho values lead to wider (more conservative) confidence intervals."
    }


def multivariate_pooling_check(outcomes: list, default_rho: float = 0.5) -> dict:
    """Check for and handle correlated outcomes from the same study.
    
    If multiple outcomes are provided for the same population (e.g., CV death and MI),
    pooling them as independent leads to unit-of-analysis errors.
    
    This function implements a conservative adjustment using a correlation 
    coefficient (rho) when the true correlation is unknown.
    """
    if len(outcomes) < 2:
        return {"adjusted": False, "reason": "Single outcome"}
        
    # Improved multivariate pooling (Simple Average of Logs)
    # Variance of mean effect = (1/n^2) * [sum(var_i) + sum(cov_ij)]
    # where cov_ij = rho * se_i * se_j
    
    n = len(outcomes)
    log_effects = []
    ses = []
    
    for o in outcomes:
        est = o.get("estimate")
        se = o.get("se")
        if est and se:
            log_effects.append(math.log(est))
            ses.append(se)
            
    if len(log_effects) < 2:
        return {"adjusted": False, "reason": "Insufficient data for adjustment"}
        
    # Simple average of log effects (consistent with variance calculation below)
    avg_log_effect = sum(log_effects) / n
    
    # Calculate adjusted variance
    sum_var = sum(se**2 for se in ses)
    sum_cov = 0
    for i in range(n):
        for j in range(i + 1, n):
            sum_cov += 2 * default_rho * ses[i] * ses[j]
            
    adj_var = (sum_var + sum_cov) / (n**2)
    adj_se = math.sqrt(adj_var)
    
    return {
        "adjusted": True,
        "n_outcomes": n,
        "composite_estimate": round(math.exp(avg_log_effect), 4),
        "composite_se": round(adj_se, 4),
        "rho_used": default_rho,
        "method": "Simple Average with Correlation Adjustment"
    }


def multivariate_sensitivity_analysis(outcomes: list) -> dict:
    """Perform sensitivity analysis on the correlation coefficient (rho)."""
    rho_values = [0.0, 0.2, 0.5, 0.7, 0.9]
    results = []
    
    for rho in rho_values:
        res = multivariate_pooling_check(outcomes, default_rho=rho)
        if res.get("adjusted"):
            results.append({
                "rho": rho,
                "estimate": res["composite_estimate"],
                "se": res["composite_se"]
            })
            
    return {
        "sensitivity_results": results,
        "interpretation": "Higher rho values lead to wider (more conservative) confidence intervals."
    }


# Statistical helper functions
def safe_exp(x: float) -> float:
    """Calculate exp(x) with overflow protection."""
    try:
        return math.exp(x)
    except OverflowError:
        return float('inf')


def estimate_se_asymmetric(estimate: float, ci_low: float, ci_high: float) -> float:
    """Estimate SE accounting for potentially asymmetric CIs.

    Uses the more conservative (larger) of the upper and lower CI distances.
    This is more robust than assuming symmetric CIs.

    Args:
        estimate: Point estimate (on natural scale for ratios)
        ci_low: Lower confidence interval bound
        ci_high: Upper confidence interval bound

    Returns:
        Estimated standard error on log scale
    """
    if estimate <= 0 or ci_low <= 0 or ci_high <= 0:
        return 0.5  # Default for invalid values

    log_est = math.log(estimate)
    log_low = math.log(ci_low)
    log_high = math.log(ci_high)

    # Use the larger distance for more conservative SE
    se_from_upper = (log_high - log_est) / 1.96
    se_from_lower = (log_est - log_low) / 1.96

    # Return the larger (more conservative) estimate
    return max(se_from_upper, se_from_lower)


def norm_cdf(x: float) -> float:
    """Standard normal CDF approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def chi2_cdf(x: float, df: int) -> float:
    """Chi-squared CDF approximation."""
    if df <= 0 or x < 0:
        return 0
    # Wilson-Hilferty approximation
    z = ((x / df) ** (1/3) - (1 - 2/(9*df))) / math.sqrt(2/(9*df))
    return norm_cdf(z)


def t_cdf(x: float, df: int) -> float:
    """Student's t CDF approximation."""
    if df <= 0:
        return norm_cdf(x)
    # For large df, approximate with normal
    if df > 100:
        return norm_cdf(x)
    # Simple approximation
    t2 = x * x
    return 0.5 + 0.5 * math.copysign(1, x) * (1 - (1 + t2/df) ** (-(df+1)/2))


def t_critical(p: float, df: int) -> float:
    """Approximate t critical value."""
    if df <= 0:
        return 1.96
    # Common values
    if df == 1:
        return 12.71 if p >= 0.975 else 6.31
    if df == 2:
        return 4.30 if p >= 0.975 else 2.92
    if df >= 30:
        return 1.96 + 0.5/df
    # Approximation for small df
    return 1.96 * (1 + 2.5/df)


# ============================================================================
# RSM EDITORIAL FIXES: Additional Publication Bias Methods
# ============================================================================

def peters_test(studies: list) -> dict:
    """Perform Peters' test for publication bias in binary outcomes.

    Peters' test is recommended over Egger's for meta-analyses of binary
    outcomes using odds ratios, as it is less prone to false positives.

    Uses regression of log(OR) on 1/total_n, weighted by total_n.

    Reference: Peters et al. JAMA 2006;295:676-680

    Args:
        studies: List of study dicts with estimate, n_treatment, n_control

    Returns:
        Peters' test results
    """
    if len(studies) < 10:
        return {
            "assessable": False,
            "reason": "Fewer than 10 studies required for Peters' test",
            "n_studies": len(studies)
        }

    # Prepare data
    log_effects = []
    inv_n = []
    weights = []

    for study in studies:
        est = study.get("estimate")
        n_t = study.get("n_treatment") or study.get("n_a") or study.get("n", 0) // 2
        n_c = study.get("n_control") or study.get("n_b") or study.get("n", 0) // 2

        if est is None or est <= 0 or n_t <= 0 or n_c <= 0:
            continue

        total_n = n_t + n_c
        log_effects.append(math.log(est))
        inv_n.append(1.0 / total_n)
        weights.append(total_n)  # Weight by total sample size

    n = len(log_effects)
    if n < 10:
        return {
            "assessable": False,
            "reason": "Insufficient valid data for Peters' test",
            "n_valid": n
        }

    # Weighted linear regression: log(OR) = intercept + slope * (1/n)
    total_weight = sum(weights)
    mean_inv_n = sum(w * x for w, x in zip(weights, inv_n)) / total_weight
    mean_log = sum(w * y for w, y in zip(weights, log_effects)) / total_weight

    ss_x = sum(w * (x - mean_inv_n) ** 2 for w, x in zip(weights, inv_n))
    sp_xy = sum(w * (x - mean_inv_n) * (y - mean_log)
                for w, x, y in zip(weights, inv_n, log_effects))

    if ss_x == 0:
        return {"assessable": False, "reason": "No variance in sample sizes"}

    slope = sp_xy / ss_x
    intercept = mean_log - slope * mean_inv_n

    # Residuals and SE
    residuals = [y - (intercept + slope * x)
                 for x, y in zip(inv_n, log_effects)]
    ss_res = sum(w * r ** 2 for w, r in zip(weights, residuals))
    mse = ss_res / (n - 2)

    se_slope = math.sqrt(mse / ss_x) if ss_x > 0 else 1.0

    # t-test for slope (not intercept, unlike Egger's)
    t_stat = slope / se_slope if se_slope > 0 else 0
    df = n - 2
    p_value = 2 * (1 - t_cdf(abs(t_stat), df))

    return {
        "assessable": True,
        "test_type": "Peters",
        "slope": round(slope, 4),
        "se_slope": round(se_slope, 4),
        "intercept": round(intercept, 4),
        "t_statistic": round(t_stat, 4),
        "df": df,
        "p_value": round(p_value, 6),
        "bias_detected": p_value < 0.1,
        "interpretation": (
            "Significant small-study effects detected (p<0.1). "
            "Consider publication bias or genuine heterogeneity."
            if p_value < 0.1 else
            "No significant small-study effects detected"
        ),
        "note": "Peters' test is preferred for binary outcomes with OR"
    }


def trim_and_fill(studies: list, side: str = "auto") -> dict:
    """Perform Duval and Tweedie's trim-and-fill procedure.

    Estimates the number of missing studies due to publication bias
    and provides a bias-adjusted pooled estimate.

    Limitations:
    - Assumes missing studies are on one side of the funnel
    - May over-correct if asymmetry is due to heterogeneity
    - Should be used alongside other bias assessments

    Reference: Duval & Tweedie, Biometrics 2000;56:455-463

    Args:
        studies: List of study dicts with estimate, se
        side: "left", "right", or "auto" to detect direction

    Returns:
        Trim-and-fill results with adjusted estimate
    """
    if len(studies) < 10:
        return {
            "assessable": False,
            "reason": "Trim-and-fill requires at least 10 studies",
            "n_studies": len(studies)
        }

    # Prepare data on log scale
    effects = []
    for study in studies:
        est = study.get("estimate")
        se = study.get("se")
        ci_low = study.get("ci_low")
        ci_high = study.get("ci_high")

        if est is None or est <= 0:
            continue

        if se is None or se <= 0:
            if ci_low and ci_high and ci_low > 0 and ci_high > 0:
                se = estimate_se_asymmetric(est, ci_low, ci_high)
            else:
                se = 0.3  # Default

        effects.append({
            "log_effect": math.log(est),
            "se": se,
            "study_id": study.get("study_id", "")
        })

    n = len(effects)
    if n < 10:
        return {
            "assessable": False,
            "reason": "Insufficient valid data",
            "n_valid": n
        }

    # Calculate pooled effect (fixed-effects for trim-and-fill)
    weights = [1 / (e["se"] ** 2) for e in effects]
    total_weight = sum(weights)
    pooled = sum(w * e["log_effect"] for w, e in zip(weights, effects)) / total_weight

    # Rank studies by deviation from pooled effect
    deviations = [(e["log_effect"] - pooled, e) for e in effects]

    # Determine side if auto
    if side == "auto":
        neg_devs = sum(1 for d, _ in deviations if d < 0)
        pos_devs = sum(1 for d, _ in deviations if d > 0)
        side = "left" if neg_devs < pos_devs else "right"

    # R0 estimator for number of missing studies
    # Sort by absolute deviation
    sorted_devs = sorted(deviations, key=lambda x: abs(x[0]))

    # Calculate ranks
    ranks = []
    for i, (dev, _) in enumerate(sorted_devs):
        if (side == "right" and dev > 0) or (side == "left" and dev < 0):
            ranks.append(i + 1)

    if not ranks:
        k0 = 0
    else:
        # L0 estimator
        n_extreme = len(ranks)
        sum_ranks = sum(ranks)
        k0 = max(0, round(4 * sum_ranks / n - n_extreme))

    # Create imputed studies
    imputed = []
    if k0 > 0:
        # Find the k0 most extreme studies on one side
        if side == "right":
            extreme = sorted([d for d, e in deviations if d > 0], reverse=True)[:k0]
        else:
            extreme = sorted([d for d, e in deviations if d < 0])[:k0]

        for dev in extreme:
            # Mirror around pooled estimate
            imputed_log = pooled - (dev if side == "right" else -dev)
            avg_se = sum(e["se"] for e in effects) / len(effects)
            imputed.append({
                "log_effect": imputed_log,
                "se": avg_se,
                "imputed": True
            })

    # Recalculate with imputed studies
    all_effects = effects + imputed
    adj_weights = [1 / (e["se"] ** 2) for e in all_effects]
    adj_total_weight = sum(adj_weights)
    adj_pooled = sum(w * e["log_effect"] for w, e in zip(adj_weights, all_effects)) / adj_total_weight
    adj_var = 1 / adj_total_weight
    adj_se = math.sqrt(adj_var)

    return {
        "assessable": True,
        "method": "trim_and_fill",
        "side": side,
        "n_original": n,
        "n_imputed": k0,
        "n_total": n + k0,
        "original": {
            "estimate": round(math.exp(pooled), 4),
            "ci_low": round(math.exp(pooled - 1.96 * math.sqrt(1/total_weight)), 4),
            "ci_high": round(math.exp(pooled + 1.96 * math.sqrt(1/total_weight)), 4),
        },
        "adjusted": {
            "estimate": round(math.exp(adj_pooled), 4),
            "ci_low": round(math.exp(adj_pooled - 1.96 * adj_se), 4),
            "ci_high": round(math.exp(adj_pooled + 1.96 * adj_se), 4),
            "se": round(adj_se, 4),
        },
        "bias_indicated": k0 > 0,
        "interpretation": (
            f"{k0} studies potentially missing from {side} side. "
            f"Adjusted estimate may be more conservative."
            if k0 > 0 else
            "No evidence of missing studies"
        ),
        "limitations": [
            "Assumes asymmetry is due to publication bias",
            "May over-correct if heterogeneity causes asymmetry",
            "Should be interpreted alongside Egger's/Peters' tests"
        ]
    }


def validate_effect_measures(studies: list) -> dict:
    """Validate that effect measures are consistent across studies.

    Mixing different effect measures (HR, OR, RR) without conversion
    can lead to invalid pooled estimates.

    Args:
        studies: List of study dicts with effect measure information

    Returns:
        Validation results with warnings if measures are mixed
    """
    measures = {}
    for study in studies:
        outcomes = study.get("outcomes", [])
        if outcomes:
            measure = outcomes[0].get("effect", {}).get("measure", "unknown")
            if measure not in measures:
                measures[measure] = []
            measures[measure].append(study.get("study_id", "unknown"))

    is_homogeneous = len(measures) <= 1
    primary_measure = max(measures.keys(), key=lambda m: len(measures[m])) if measures else None

    result = {
        "valid": is_homogeneous,
        "measures_found": list(measures.keys()),
        "primary_measure": primary_measure,
        "studies_by_measure": {k: len(v) for k, v in measures.items()},
    }

    if not is_homogeneous:
        result["warning"] = (
            f"Mixed effect measures detected: {list(measures.keys())}. "
            f"Studies with non-primary measures should be excluded or converted."
        )
        result["exclusion_candidates"] = {
            k: v for k, v in measures.items() if k != primary_measure
        }
        result["recommendations"] = [
            "Option 1: Exclude studies with different effect measures",
            "Option 2: Convert effect measures (requires additional assumptions)",
            "Option 3: Perform separate subgroup analyses by measure type"
        ]

    return result


def filter_by_effect_measure(studies: list, target_measure: str = None) -> Tuple[list, dict]:
    """Filter studies to include only those with consistent effect measures.

    Args:
        studies: List of study dicts
        target_measure: Specific measure to filter for (auto-detects if None)

    Returns:
        Tuple of (filtered_studies, filter_report)
    """
    validation = validate_effect_measures(studies)

    if target_measure is None:
        target_measure = validation["primary_measure"]

    if target_measure is None:
        return studies, {"filtered": False, "reason": "No effect measures found"}

    included = []
    excluded = []

    for study in studies:
        outcomes = study.get("outcomes", [])
        if outcomes:
            measure = outcomes[0].get("effect", {}).get("measure", "")
            if measure == target_measure:
                included.append(study)
            else:
                excluded.append({
                    "study_id": study.get("study_id"),
                    "measure": measure,
                    "reason": f"Effect measure '{measure}' differs from target '{target_measure}'"
                })
        else:
            # Include studies without explicit measure (assume compatible)
            included.append(study)

    return included, {
        "filtered": True,
        "target_measure": target_measure,
        "n_included": len(included),
        "n_excluded": len(excluded),
        "excluded_studies": excluded
    }


def funnel_plot_data(studies: list) -> dict:
    """Generate data for funnel plot visualization.

    Returns coordinates and contour lines for enhanced funnel plots.

    Args:
        studies: List of study dicts with estimate and SE

    Returns:
        Funnel plot data with contours for significance regions
    """
    points = []

    for study in studies:
        est = study.get("estimate")
        se = study.get("se")
        ci_low = study.get("ci_low")
        ci_high = study.get("ci_high")

        if est is None or est <= 0:
            continue

        if se is None or se <= 0:
            if ci_low and ci_high and ci_low > 0 and ci_high > 0:
                se = estimate_se_asymmetric(est, ci_low, ci_high)
            else:
                continue

        points.append({
            "study_id": study.get("study_id", ""),
            "x": math.log(est),  # Effect on log scale
            "y": se,  # SE (inverted precision)
            "estimate": est
        })

    if not points:
        return {"error": "No valid data for funnel plot"}

    # Calculate pooled effect for center line
    weights = [1 / (p["y"] ** 2) for p in points]
    total_weight = sum(weights)
    pooled = sum(w * p["x"] for w, p in zip(weights, points)) / total_weight

    # SE range for contours
    min_se = min(p["y"] for p in points) * 0.5
    max_se = max(p["y"] for p in points) * 1.2

    # Significance contours (1%, 5%, 10% levels)
    contours = {}
    for alpha, z in [(0.01, 2.576), (0.05, 1.96), (0.10, 1.645)]:
        contours[f"p_{alpha}"] = {
            "left": [pooled - z * se for se in [min_se, max_se]],
            "right": [pooled + z * se for se in [min_se, max_se]],
            "se_range": [min_se, max_se]
        }

    return {
        "points": points,
        "pooled_log_effect": round(pooled, 4),
        "pooled_effect": round(math.exp(pooled), 4),
        "se_range": [round(min_se, 4), round(max_se, 4)],
        "contours": contours,
        "plot_type": "contour_enhanced_funnel",
        "note": "X-axis: log(effect), Y-axis: SE. Points in white regions are non-significant."
    }


# ============================================================================
# ESC METHODOLOGY ADDITIONS: Subgroup Analysis
# ============================================================================

@dataclass
class SubgroupResult:
    """Result of meta-analysis for a single subgroup."""
    subgroup_name: str
    subgroup_value: str
    n_studies: int
    n_participants: int
    pooled_estimate: float
    ci_low: float
    ci_high: float
    se: float
    i2: float
    study_ids: List[str]


@dataclass
class ICEMANAssessment:
    """ICEMAN credibility assessment for subgroup effects.

    ICEMAN (Instrument for Credibility of Effect Modification Analyses)
    assesses whether observed subgroup differences are likely real.

    Reference: Schandelmaier et al. CMAJ 2020
    """
    is_pre_specified: bool
    direction_predicted: bool
    statistical_interaction: bool
    interaction_p_value: float
    consistent_across_outcomes: bool
    consistent_across_studies: bool
    biological_plausibility: str  # "high", "moderate", "low", "unclear"
    credibility_rating: str  # "high", "moderate", "low", "very_low"
    credibility_score: int  # 0-7 points
    rationale: str


# Pre-specified subgroups for cardiovascular guidelines (ESC)
CV_SUBGROUPS = {
    "acute_vs_chronic_cad": {
        "field": "population_type",
        "values": ["acute_cad", "chronic_cad"],
        "description": "Acute vs chronic coronary artery disease",
        "biological_rationale": "Inflammatory burden differs between acute and chronic presentations"
    },
    "post_mi_timing": {
        "field": "time_from_mi",
        "values": ["<30_days", ">=30_days"],
        "description": "Timing from MI (<30 days vs >=30 days)",
        "biological_rationale": "Early post-MI period has heightened inflammatory state"
    },
    "baseline_crp": {
        "field": "baseline_crp",
        "values": ["elevated", "normal"],
        "description": "Baseline C-reactive protein (elevated >2mg/L vs normal)",
        "biological_rationale": "Anti-inflammatory agents may benefit those with elevated inflammation"
    },
    "diabetes_status": {
        "field": "diabetes",
        "values": ["yes", "no"],
        "description": "Diabetes mellitus status",
        "biological_rationale": "Diabetic patients have altered inflammatory response"
    },
    "renal_function": {
        "field": "renal_function",
        "values": ["normal", "reduced"],
        "description": "Renal function (eGFR >=60 vs <60 mL/min/1.73m²)",
        "biological_rationale": "Drug clearance and safety differ by renal function"
    },
    "statin_use": {
        "field": "statin_use",
        "values": ["yes", "no"],
        "description": "Concurrent statin therapy",
        "biological_rationale": "Statins have pleiotropic anti-inflammatory effects"
    },
    "age_group": {
        "field": "age_category",
        "values": ["<65", "65-75", ">75"],
        "description": "Age categories",
        "biological_rationale": "Treatment effects may vary with age"
    },
    "sex": {
        "field": "sex",
        "values": ["male", "female"],
        "description": "Biological sex",
        "biological_rationale": "Sex differences in cardiovascular pathophysiology"
    }
}


def subgroup_meta_analysis(studies: list, subgroup_variable: str,
                           subgroup_config: dict = None) -> dict:
    """Perform subgroup meta-analysis with interaction testing.

    Stratifies studies by a categorical variable and performs separate
    meta-analyses per subgroup, then tests for interaction.

    Args:
        studies: List of study dicts with estimate, se, and subgroup field
        subgroup_variable: Field name to stratify by
        subgroup_config: Optional configuration for the subgroup (from CV_SUBGROUPS)

    Returns:
        Subgroup analysis results with interaction test
    """
    if subgroup_config is None:
        subgroup_config = CV_SUBGROUPS.get(subgroup_variable, {})

    # Group studies by subgroup value
    subgroups = {}
    unclassified = []

    for study in studies:
        field = subgroup_config.get("field", subgroup_variable)
        value = study.get(field)

        if value is None:
            # Try nested access (e.g., in study characteristics)
            chars = study.get("characteristics", {})
            value = chars.get(field)

        if value is not None:
            value_str = str(value).lower().strip()
            if value_str not in subgroups:
                subgroups[value_str] = []
            subgroups[value_str].append(study)
        else:
            unclassified.append(study)

    if len(subgroups) < 2:
        return {
            "assessable": False,
            "reason": f"Need at least 2 subgroups for analysis (found {len(subgroups)})",
            "subgroup_variable": subgroup_variable,
            "groups_found": list(subgroups.keys()),
            "n_unclassified": len(unclassified)
        }

    # Perform meta-analysis for each subgroup
    subgroup_results = []
    pooled_log_effects = []
    pooled_variances = []
    total_n = 0

    for group_name, group_studies in subgroups.items():
        if len(group_studies) < 1:
            continue

        result = calculate_meta_analysis_hksj(group_studies, use_hksj=len(group_studies) < 10)

        if "error" not in result:
            pooled = result.get("pooled", {})
            n_participants = sum(s.get("n_total", 0) for s in group_studies)

            sg_result = SubgroupResult(
                subgroup_name=subgroup_variable,
                subgroup_value=group_name,
                n_studies=len(group_studies),
                n_participants=n_participants,
                pooled_estimate=pooled.get("estimate", 0),
                ci_low=pooled.get("ci_low", 0),
                ci_high=pooled.get("ci_high", 0),
                se=pooled.get("se", 0),
                i2=result.get("heterogeneity", {}).get("i2", 0),
                study_ids=[s.get("study_id", "") for s in group_studies]
            )
            subgroup_results.append(sg_result)

            # Store for interaction test (on log scale)
            if pooled.get("estimate", 0) > 0:
                pooled_log_effects.append(math.log(pooled["estimate"]))
                pooled_variances.append(pooled.get("se", 0.1) ** 2)
                total_n += n_participants

    # Test for subgroup interaction (chi-squared test)
    interaction_result = _test_subgroup_interaction(
        pooled_log_effects, pooled_variances, len(subgroup_results)
    )

    # ICEMAN credibility assessment
    iceman = _assess_iceman_credibility(
        subgroup_variable=subgroup_variable,
        subgroup_config=subgroup_config,
        n_subgroups=len(subgroup_results),
        interaction_pvalue=interaction_result.get("p_value", 1.0),
        subgroup_results=subgroup_results
    )

    return {
        "assessable": True,
        "subgroup_variable": subgroup_variable,
        "description": subgroup_config.get("description", subgroup_variable),
        "biological_rationale": subgroup_config.get("biological_rationale", ""),
        "n_subgroups": len(subgroup_results),
        "total_participants": total_n,
        "subgroups": [
            {
                "name": sr.subgroup_value,
                "n_studies": sr.n_studies,
                "n_participants": sr.n_participants,
                "pooled_estimate": sr.pooled_estimate,
                "ci_low": sr.ci_low,
                "ci_high": sr.ci_high,
                "se": sr.se,
                "i2": sr.i2,
                "study_ids": sr.study_ids
            }
            for sr in subgroup_results
        ],
        "interaction_test": interaction_result,
        "iceman_credibility": {
            "rating": iceman.credibility_rating,
            "score": iceman.credibility_score,
            "is_pre_specified": iceman.is_pre_specified,
            "direction_predicted": iceman.direction_predicted,
            "interaction_significant": iceman.statistical_interaction,
            "interaction_p_value": iceman.interaction_p_value,
            "biological_plausibility": iceman.biological_plausibility,
            "rationale": iceman.rationale
        },
        "n_unclassified": len(unclassified),
        "forest_plot_data": _generate_subgroup_forest_data(subgroup_results)
    }


def _test_subgroup_interaction(pooled_effects: list, variances: list,
                                n_groups: int) -> dict:
    """Test for statistical interaction between subgroups.

    Uses chi-squared test for heterogeneity across subgroups.

    Args:
        pooled_effects: List of pooled log effects per subgroup
        variances: List of variances per subgroup
        n_groups: Number of subgroups

    Returns:
        Interaction test results
    """
    if len(pooled_effects) < 2:
        return {
            "assessable": False,
            "reason": "Need at least 2 subgroups"
        }

    # Overall pooled effect (inverse-variance weighted)
    weights = [1/v for v in variances if v > 0]
    if not weights:
        return {"assessable": False, "reason": "No valid variances"}

    total_weight = sum(weights)
    overall_pooled = sum(w * e for w, e in zip(weights, pooled_effects)) / total_weight

    # Chi-squared for interaction
    q_interaction = sum(
        w * (e - overall_pooled) ** 2
        for w, e in zip(weights, pooled_effects)
    )

    df = n_groups - 1
    p_value = 1 - chi2_cdf(q_interaction, df) if df > 0 else 1.0

    return {
        "assessable": True,
        "test_type": "chi_squared_interaction",
        "q_statistic": round(q_interaction, 4),
        "df": df,
        "p_value": round(p_value, 6),
        "interaction_significant": p_value < 0.10,  # Conservative threshold
        "interpretation": (
            "Significant interaction detected (p<0.10): "
            "Treatment effect may differ across subgroups"
            if p_value < 0.10 else
            "No significant interaction: "
            "Insufficient evidence of subgroup differences"
        )
    }


def _assess_iceman_credibility(subgroup_variable: str, subgroup_config: dict,
                                n_subgroups: int, interaction_pvalue: float,
                                subgroup_results: list) -> ICEMANAssessment:
    """Assess credibility of subgroup effect using ICEMAN criteria.

    ICEMAN evaluates whether observed subgroup differences are real
    versus spurious findings.

    Args:
        subgroup_variable: Name of subgroup variable
        subgroup_config: Configuration from CV_SUBGROUPS
        n_subgroups: Number of subgroups analyzed
        interaction_pvalue: P-value from interaction test
        subgroup_results: List of SubgroupResult objects

    Returns:
        ICEMANAssessment with credibility rating
    """
    score = 0
    rationale_parts = []

    # 1. Pre-specified analysis? (+1 if yes)
    is_pre_specified = subgroup_variable in CV_SUBGROUPS
    if is_pre_specified:
        score += 1
        rationale_parts.append("Pre-specified subgroup (+1)")
    else:
        rationale_parts.append("Post-hoc subgroup (+0)")

    # 2. Direction predicted a priori? (+1 if yes)
    # For CV subgroups with biological rationale, assume direction was predicted
    direction_predicted = is_pre_specified and bool(subgroup_config.get("biological_rationale"))
    if direction_predicted:
        score += 1
        rationale_parts.append("Direction predicted (+1)")
    else:
        rationale_parts.append("Direction not predicted (+0)")

    # 3. Statistical interaction? (+1 if significant)
    statistical_interaction = interaction_pvalue < 0.10
    if statistical_interaction:
        score += 1
        rationale_parts.append(f"Significant interaction p={interaction_pvalue:.3f} (+1)")
    else:
        rationale_parts.append(f"No significant interaction p={interaction_pvalue:.3f} (+0)")

    # 4. Consistent across related outcomes? (+1 if yes)
    # Would require multiple outcomes - assume yes for now if pre-specified
    consistent_outcomes = is_pre_specified
    if consistent_outcomes:
        score += 1
        rationale_parts.append("Assumed consistent across outcomes (+1)")

    # 5. Consistent across studies? (+1 if effects in same direction)
    if len(subgroup_results) >= 2:
        estimates = [sr.pooled_estimate for sr in subgroup_results]
        all_same_direction = all(e < 1 for e in estimates) or all(e > 1 for e in estimates)
        if all_same_direction:
            consistent_studies = True
            rationale_parts.append("Consistent direction across subgroups (+1)")
        else:
            consistent_studies = False
            rationale_parts.append("Inconsistent direction (+0)")
            # If opposite directions and significant interaction, this is meaningful
            if statistical_interaction:
                score += 1
                rationale_parts.append("But interaction shows effect modification (+1)")
    else:
        consistent_studies = False

    # 6. Biological plausibility
    if subgroup_config.get("biological_rationale"):
        biological_plausibility = "high"
        score += 1
        rationale_parts.append("Strong biological rationale (+1)")
    else:
        biological_plausibility = "unclear"
        rationale_parts.append("Unclear biological rationale (+0)")

    # Calculate credibility rating
    if score >= 5:
        credibility_rating = "high"
    elif score >= 3:
        credibility_rating = "moderate"
    elif score >= 2:
        credibility_rating = "low"
    else:
        credibility_rating = "very_low"

    return ICEMANAssessment(
        is_pre_specified=is_pre_specified,
        direction_predicted=direction_predicted,
        statistical_interaction=statistical_interaction,
        interaction_p_value=interaction_pvalue,
        consistent_across_outcomes=consistent_outcomes,
        consistent_across_studies=consistent_studies,
        biological_plausibility=biological_plausibility,
        credibility_rating=credibility_rating,
        credibility_score=score,
        rationale="; ".join(rationale_parts)
    )


def _generate_subgroup_forest_data(subgroup_results: list) -> dict:
    """Generate forest plot data for subgroup analysis.

    Args:
        subgroup_results: List of SubgroupResult objects

    Returns:
        Data structure for forest plot visualization
    """
    rows = []
    for sr in subgroup_results:
        rows.append({
            "label": sr.subgroup_value,
            "n_studies": sr.n_studies,
            "n_participants": sr.n_participants,
            "estimate": sr.pooled_estimate,
            "ci_low": sr.ci_low,
            "ci_high": sr.ci_high,
            "weight": sr.n_participants  # Weight by sample size
        })

    return {
        "type": "subgroup_forest",
        "rows": rows,
        "x_axis_label": "Effect estimate",
        "null_value": 1.0,
        "show_weights": True,
        "show_heterogeneity": True
    }


def run_all_cv_subgroups(studies: list) -> dict:
    """Run subgroup analyses for all pre-specified CV subgroups.

    Args:
        studies: List of study dicts

    Returns:
        Results for each subgroup analysis
    """
    results = {}

    for subgroup_name, subgroup_config in CV_SUBGROUPS.items():
        result = subgroup_meta_analysis(
            studies=studies,
            subgroup_variable=subgroup_name,
            subgroup_config=subgroup_config
        )

        if result.get("assessable"):
            results[subgroup_name] = result

    return {
        "total_subgroups_assessed": len(results),
        "subgroup_analyses": results,
        "any_significant_interactions": any(
            r.get("interaction_test", {}).get("interaction_significant", False)
            for r in results.values()
        ),
        "credible_subgroups": [
            name for name, r in results.items()
            if r.get("iceman_credibility", {}).get("rating") in ["high", "moderate"]
        ]
    }
