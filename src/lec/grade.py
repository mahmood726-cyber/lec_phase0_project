"""GRADE Certainty Assessment Framework.

Implements GRADE (Grading of Recommendations Assessment, Development and Evaluation)
for assessing certainty of evidence in meta-analyses.

Domains:
1. Risk of Bias
2. Inconsistency (heterogeneity)
3. Indirectness
4. Imprecision
5. Publication Bias
"""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
import math

from lec.core import utc_now_iso


class GradeLevel(Enum):
    """GRADE certainty levels."""
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"


class DowngradeReason(Enum):
    """Reasons for downgrading certainty."""
    RISK_OF_BIAS = "risk_of_bias"
    INCONSISTENCY = "inconsistency"
    INDIRECTNESS = "indirectness"
    IMPRECISION = "imprecision"
    PUBLICATION_BIAS = "publication_bias"


class UpgradeReason(Enum):
    """Reasons for upgrading certainty (observational studies only per GRADE).

    Per GRADE methodology, upgrades can only apply to observational studies
    that start at LOW certainty. RCTs starting at HIGH cannot be upgraded.
    """
    LARGE_EFFECT = "large_effect"
    DOSE_RESPONSE = "dose_response"
    PLAUSIBLE_CONFOUNDING = "plausible_confounding"


@dataclass
class DomainAssessment:
    """Assessment for a single GRADE domain."""
    domain: str
    rating: str  # "no_concern", "serious", "very_serious"
    downgrade: int  # 0, 1, or 2 levels
    rationale: str
    details: dict = field(default_factory=dict)


@dataclass
class UpgradeAssessment:
    """Assessment for a GRADE upgrade domain.

    Per GRADE methodology:
    - Large effect: RR/OR > 5 or < 0.2 (very large), or > 2 or < 0.5 (large)
    - Dose-response: Evidence of gradient across doses/exposures
    - Plausible confounding: Residual confounding would reduce demonstrated effect
    """
    domain: str
    upgrade: int  # 0 or 1 level
    applicable: bool  # Whether upgrade criteria were assessed
    rationale: str
    details: dict = field(default_factory=dict)


@dataclass
class GradeAssessment:
    """Complete GRADE assessment for a body of evidence."""
    outcome_name: str
    n_studies: int
    n_participants: int
    starting_level: str = "high"  # RCTs start high, observational starts low
    domains: List[DomainAssessment] = field(default_factory=list)
    upgrades: List[UpgradeAssessment] = field(default_factory=list)
    final_level: GradeLevel = GradeLevel.HIGH
    summary: str = ""
    assessed_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "outcome_name": self.outcome_name,
            "n_studies": self.n_studies,
            "n_participants": self.n_participants,
            "starting_level": self.starting_level,
            "domains": [
                {
                    "domain": d.domain,
                    "rating": d.rating,
                    "downgrade": d.downgrade,
                    "rationale": d.rationale,
                    "details": d.details
                }
                for d in self.domains
            ],
            "upgrades": [
                {
                    "domain": u.domain,
                    "upgrade": u.upgrade,
                    "applicable": u.applicable,
                    "rationale": u.rationale,
                    "details": u.details
                }
                for u in self.upgrades
            ],
            "final_level": self.final_level.value,
            "total_downgrade": sum(d.downgrade for d in self.domains),
            "total_upgrade": sum(u.upgrade for u in self.upgrades),
            "summary": self.summary,
            "assessed_at": self.assessed_at
        }


class GradeAssessor:
    """Automated GRADE certainty assessment."""

    # Thresholds for automatic assessment
    HETEROGENEITY_THRESHOLDS = {
        "no_concern": 40,  # I² < 40%
        "serious": 60,     # I² 40-60%
        "very_serious": 75  # I² > 75%
    }

    IMPRECISION_THRESHOLDS = {
        "ois": 300,  # Optimal Information Size
        "ci_width_ratio": 0.5,  # CI width relative to effect
    }

    # GRADE upgrade thresholds (per GRADE handbook)
    LARGE_EFFECT_THRESHOLDS = {
        "large": {"rr_upper": 2.0, "rr_lower": 0.5},  # +1 upgrade
        "very_large": {"rr_upper": 5.0, "rr_lower": 0.2}  # +2 upgrade (capped at +1 per domain)
    }

    DOSE_RESPONSE_THRESHOLDS = {
        "p_trend": 0.05,  # p-value for trend test
        "min_doses": 3  # Minimum dose levels for assessment
    }

    def __init__(self, study_design: str = "rct"):
        """Initialize assessor.

        Args:
            study_design: "rct" (starts HIGH) or "observational" (starts LOW)
        """
        self.study_design = study_design
        self.starting_level = "high" if study_design == "rct" else "low"

    def assess(self, meta_results: dict, studies: list,
               outcome_name: str = "primary") -> GradeAssessment:
        """Perform GRADE assessment on meta-analysis results.

        Args:
            meta_results: Results from meta-analysis (pooled, heterogeneity)
            studies: List of study data
            outcome_name: Name of outcome being assessed

        Returns:
            Complete GRADE assessment
        """
        n_studies = len(studies)
        n_participants = sum(s.get("n_total", 0) for s in studies)

        assessment = GradeAssessment(
            outcome_name=outcome_name,
            n_studies=n_studies,
            n_participants=n_participants,
            starting_level=self.starting_level
        )

        # Assess each downgrade domain
        assessment.domains.append(self._assess_risk_of_bias(studies))
        assessment.domains.append(self._assess_inconsistency(meta_results))
        assessment.domains.append(self._assess_indirectness(studies))
        assessment.domains.append(self._assess_imprecision(meta_results, n_participants))
        assessment.domains.append(self._assess_publication_bias(meta_results, n_studies))

        # Assess upgrade domains (per GRADE, primarily for observational studies
        # but also assessed for RCTs to document when large effects exist)
        assessment.upgrades.append(self._assess_large_effect(meta_results))
        assessment.upgrades.append(self._assess_dose_response(studies))
        assessment.upgrades.append(self._assess_plausible_confounding(studies))

        # Calculate final level (downgrades first, then upgrades)
        total_downgrade = sum(d.downgrade for d in assessment.domains)
        total_upgrade = sum(u.upgrade for u in assessment.upgrades)
        assessment.final_level = self._calculate_final_level(total_downgrade, total_upgrade)

        # Generate summary
        assessment.summary = self._generate_summary(assessment)

        return assessment

    def _assess_risk_of_bias(self, studies: list) -> DomainAssessment:
        """Assess risk of bias domain using RoB 2.0 criteria.
        
        Domains:
        D1: Randomization process
        D2: Deviations from intended interventions
        D3: Missing outcome data
        D4: Measurement of the outcome
        D5: Selection of the reported result
        """
        n_studies = len(studies)
        if n_studies == 0:
            return DomainAssessment("risk_of_bias", "no_concern", 0, "No studies")

        # Map internal risk of bias keys to RoB 2.0 domains
        rob2_stats = {
            "D1": {"low": 0, "unclear": 0, "high": 0},
            "D2": {"low": 0, "unclear": 0, "high": 0},
            "D3": {"low": 0, "unclear": 0, "high": 0},
            "D4": {"low": 0, "unclear": 0, "high": 0},
            "D5": {"low": 0, "unclear": 0, "high": 0},
            "overall": {"low": 0, "unclear": 0, "high": 0}
        }

        for study in studies:
            rob = study.get("risk_of_bias", {})
            
            # 1. Randomization (D1)
            d1 = rob.get("d1") or rob.get("randomization")
            if not d1:
                # Infer from allocation
                alloc = study.get("allocation", "").lower()
                d1 = "low" if "random" in alloc else "high"
            
            # 2. Others (D2-D5)
            # If missing, we'll assume "low" for Phase 0 unless overall is high
            overall = rob.get("overall", "low")
            
            # Count domains
            for d_key, key in [("D1", d1), ("D2", rob.get("d2")), ("D3", rob.get("d3")), 
                               ("D4", rob.get("d4")), ("D5", rob.get("d5")), ("overall", overall)]:
                val = str(key).lower() if key else "unclear"
                if "low" in val: rob2_stats[d_key]["low"] += 1
                elif "high" in val: rob2_stats[d_key]["high"] += 1
                else: rob2_stats[d_key]["unclear"] += 1

        # Decision Logic: Downgrade if >25% of studies have high risk in ANY domain
        high_risk_any = any(stats["high"] > n_studies * 0.25 for d, stats in rob2_stats.items())
        very_high_risk = rob2_stats["overall"]["high"] > n_studies * 0.5

        if very_high_risk:
            rating = "very_serious"
            downgrade = 2
            rationale = "Very serious risk of bias: >50% of studies at high overall risk"
        elif high_risk_any:
            rating = "serious"
            downgrade = 1
            # Find which domain caused it
            problem_domains = [d for d, s in rob2_stats.items() if s["high"] > n_studies * 0.25]
            rationale = f"Serious risk of bias: high risk in domains {', '.join(problem_domains)}"
        else:
            rating = "no_concern"
            downgrade = 0
            rationale = "Majority of evidence from studies at low risk of bias (RoB 2.0)"

        return DomainAssessment(
            domain="risk_of_bias",
            rating=rating,
            downgrade=downgrade,
            rationale=rationale,
            details=rob2_stats
        )

    def _assess_inconsistency(self, meta_results: dict) -> DomainAssessment:
        """Assess inconsistency (heterogeneity) domain."""
        heterogeneity = meta_results.get("heterogeneity", {})
        i2 = heterogeneity.get("i2", 0)
        tau2 = heterogeneity.get("tau2", 0)
        q_pvalue = heterogeneity.get("p_heterogeneity")

        if i2 < self.HETEROGENEITY_THRESHOLDS["no_concern"]:
            rating = "no_concern"
            downgrade = 0
            rationale = f"Low heterogeneity (I²={i2:.1f}%)"
        elif i2 < self.HETEROGENEITY_THRESHOLDS["serious"]:
            rating = "no_concern"
            downgrade = 0
            rationale = f"Moderate heterogeneity (I²={i2:.1f}%), but acceptable"
        elif i2 < self.HETEROGENEITY_THRESHOLDS["very_serious"]:
            rating = "serious"
            downgrade = 1
            rationale = f"Substantial heterogeneity (I²={i2:.1f}%)"
        else:
            rating = "very_serious"
            downgrade = 2
            rationale = f"Considerable heterogeneity (I²={i2:.1f}%)"

        return DomainAssessment(
            domain="inconsistency",
            rating=rating,
            downgrade=downgrade,
            rationale=rationale,
            details={
                "i2": i2,
                "tau2": tau2,
                "q_pvalue": q_pvalue,
                "interpretation": self._interpret_i2(i2)
            }
        )

    def _assess_indirectness(self, studies: list) -> DomainAssessment:
        """Assess indirectness domain."""
        # Check PICO alignment across studies
        concerns = []

        populations = set()
        interventions = set()
        comparators = set()

        for study in studies:
            pop = study.get("population", "").lower()
            interv = study.get("intervention", "").lower()
            comp = study.get("comparator", "").lower()

            if pop:
                populations.add(pop)
            if interv:
                interventions.add(interv)
            if comp:
                comparators.add(comp)

        # Multiple populations may indicate indirectness
        if len(populations) > 2:
            concerns.append(f"Heterogeneous populations ({len(populations)} types)")
        if len(interventions) > 2:
            concerns.append(f"Heterogeneous interventions ({len(interventions)} types)")

        if len(concerns) >= 2:
            rating = "serious"
            downgrade = 1
            rationale = "; ".join(concerns)
        elif len(concerns) == 1:
            rating = "no_concern"
            downgrade = 0
            rationale = f"Minor concern: {concerns[0]}"
        else:
            rating = "no_concern"
            downgrade = 0
            rationale = "Direct evidence applicable to target population"

        return DomainAssessment(
            domain="indirectness",
            rating=rating,
            downgrade=downgrade,
            rationale=rationale,
            details={
                "unique_populations": len(populations),
                "unique_interventions": len(interventions),
                "concerns": concerns
            }
        )

    def _assess_imprecision(self, meta_results: dict,
                            n_participants: int) -> DomainAssessment:
        """Assess imprecision domain."""
        pooled = meta_results.get("pooled", {})
        estimate = pooled.get("estimate")
        ci_low = pooled.get("ci_low")
        ci_high = pooled.get("ci_high")

        concerns = []
        downgrade = 0

        # Check Optimal Information Size (OIS)
        if n_participants < self.IMPRECISION_THRESHOLDS["ois"]:
            concerns.append(f"Small sample size (n={n_participants}, OIS=300)")
            downgrade += 1

        # Check CI width for clinical significance
        if estimate and ci_low and ci_high:
            # For ratio measures, check if CI crosses 1.0 (null)
            if ci_low < 1.0 < ci_high:
                concerns.append("95% CI crosses null effect (1.0)")
                downgrade = max(downgrade, 1)

            # Check if CI includes clinically important effects on both sides
            ci_width = ci_high - ci_low
            if estimate > 0:
                relative_width = ci_width / estimate
                if relative_width > 1.0:
                    concerns.append(f"Wide confidence interval (relative width: {relative_width:.2f})")
                    downgrade = max(downgrade, 1)

        if downgrade >= 2:
            rating = "very_serious"
            downgrade = 2
        elif downgrade == 1:
            rating = "serious"
        else:
            rating = "no_concern"
            concerns = ["Adequate precision"]

        return DomainAssessment(
            domain="imprecision",
            rating=rating,
            downgrade=downgrade,
            rationale="; ".join(concerns),
            details={
                "n_participants": n_participants,
                "ois_threshold": self.IMPRECISION_THRESHOLDS["ois"],
                "ci_low": ci_low,
                "ci_high": ci_high,
                "crosses_null": ci_low < 1.0 < ci_high if ci_low and ci_high else None
            }
        )

    def _assess_publication_bias(self, meta_results: dict,
                                  n_studies: int) -> DomainAssessment:
        """Assess publication bias domain."""
        pub_bias = meta_results.get("publication_bias", {})
        egger_pvalue = pub_bias.get("egger_pvalue")
        funnel_asymmetry = pub_bias.get("funnel_asymmetry")

        if n_studies < 10:
            rating = "no_concern"
            downgrade = 0
            rationale = f"Too few studies (n={n_studies}) to assess publication bias"
            details = {"assessable": False, "reason": "n < 10"}
        elif egger_pvalue is not None and egger_pvalue < 0.1:
            rating = "serious"
            downgrade = 1
            rationale = f"Egger's test suggests asymmetry (p={egger_pvalue:.3f})"
            details = {"egger_pvalue": egger_pvalue, "asymmetry_detected": True}
        elif funnel_asymmetry:
            rating = "serious"
            downgrade = 1
            rationale = "Visual funnel plot asymmetry detected"
            details = {"funnel_asymmetry": True}
        else:
            rating = "no_concern"
            downgrade = 0
            rationale = "No evidence of publication bias"
            details = {"egger_pvalue": egger_pvalue, "asymmetry_detected": False}

        return DomainAssessment(
            domain="publication_bias",
            rating=rating,
            downgrade=downgrade,
            rationale=rationale,
            details=details
        )

    def _assess_large_effect(self, meta_results: dict) -> UpgradeAssessment:
        """Assess large effect upgrade domain.

        Per GRADE: Large magnitude of effect can upgrade certainty
        - RR/OR > 2.0 or < 0.5: Large effect (+1)
        - RR/OR > 5.0 or < 0.2: Very large effect (+1, documented)

        Note: For ratio measures (RR, OR, HR), effect is considered large
        when point estimate shows strong effect away from null (1.0).
        """
        pooled = meta_results.get("pooled", {})
        estimate = pooled.get("estimate")
        ci_low = pooled.get("ci_low")
        ci_high = pooled.get("ci_high")

        if estimate is None:
            return UpgradeAssessment(
                domain="large_effect",
                upgrade=0,
                applicable=False,
                rationale="No effect estimate available for assessment",
                details={}
            )

        # For ratio measures, check magnitude relative to null (1.0)
        large_upper = self.LARGE_EFFECT_THRESHOLDS["large"]["rr_upper"]
        large_lower = self.LARGE_EFFECT_THRESHOLDS["large"]["rr_lower"]
        very_large_upper = self.LARGE_EFFECT_THRESHOLDS["very_large"]["rr_upper"]
        very_large_lower = self.LARGE_EFFECT_THRESHOLDS["very_large"]["rr_lower"]

        # Check for very large effect (RR/HR > 5 or < 0.2)
        is_very_large = estimate >= very_large_upper or estimate <= very_large_lower
        # Check for large effect (RR/HR > 2 or < 0.5)
        is_large = estimate >= large_upper or estimate <= large_lower

        # CI should also show consistent direction (not crossing null appreciably)
        ci_consistent = not (ci_low < 1.0 < ci_high)

        if is_very_large and ci_consistent:
            upgrade = 1  # Maximum per domain
            rationale = f"Very large effect (estimate={estimate:.2f}), CI consistent"
            effect_magnitude = "very_large"
        elif is_large and ci_consistent:
            upgrade = 1
            rationale = f"Large effect (estimate={estimate:.2f}), CI consistent"
            effect_magnitude = "large"
        elif is_large:
            upgrade = 0
            rationale = f"Large effect (estimate={estimate:.2f}) but CI crosses null"
            effect_magnitude = "large_uncertain"
        else:
            upgrade = 0
            rationale = f"Effect size not large enough for upgrade (estimate={estimate:.2f})"
            effect_magnitude = "not_large"

        return UpgradeAssessment(
            domain="large_effect",
            upgrade=upgrade,
            applicable=True,
            rationale=rationale,
            details={
                "estimate": estimate,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "effect_magnitude": effect_magnitude,
                "ci_consistent": ci_consistent,
                "thresholds": {
                    "large": {"upper": large_upper, "lower": large_lower},
                    "very_large": {"upper": very_large_upper, "lower": very_large_lower}
                }
            }
        )

    def _assess_dose_response(self, studies: list) -> UpgradeAssessment:
        """Assess dose-response gradient upgrade domain.

        Per GRADE: Evidence of dose-response gradient can upgrade certainty
        - Requires ≥3 dose levels across or within studies
        - p-trend < 0.05 for gradient
        - Biological plausibility of gradient direction
        """
        # Collect dose information from studies
        dose_data = []
        for study in studies:
            dose = study.get("dose")
            dose_unit = study.get("dose_unit")
            effect = study.get("effect_estimate")

            if dose is not None and effect is not None:
                dose_data.append({
                    "dose": dose,
                    "dose_unit": dose_unit,
                    "effect": effect,
                    "study_id": study.get("study_id")
                })

        n_doses = len(set(d["dose"] for d in dose_data if d["dose"]))

        if n_doses < self.DOSE_RESPONSE_THRESHOLDS["min_doses"]:
            return UpgradeAssessment(
                domain="dose_response",
                upgrade=0,
                applicable=False,
                rationale=f"Insufficient dose levels for gradient assessment (n={n_doses}, need >=3)",
                details={
                    "n_dose_levels": n_doses,
                    "dose_data_available": len(dose_data),
                    "min_required": self.DOSE_RESPONSE_THRESHOLDS["min_doses"]
                }
            )

        # Sort by dose and check for monotonic trend
        dose_data_sorted = sorted([d for d in dose_data if d["dose"]], key=lambda x: x["dose"])

        if len(dose_data_sorted) >= 3:
            # Simple gradient check: are effects monotonically changing with dose?
            effects = [d["effect"] for d in dose_data_sorted]
            is_increasing = all(effects[i] <= effects[i+1] for i in range(len(effects)-1))
            is_decreasing = all(effects[i] >= effects[i+1] for i in range(len(effects)-1))
            has_gradient = is_increasing or is_decreasing

            # Calculate simple trend correlation
            doses = [d["dose"] for d in dose_data_sorted]
            if len(doses) >= 3:
                # Spearman-like rank correlation approximation
                n = len(doses)
                dose_ranks = list(range(1, n + 1))
                effect_ranks = [sorted(effects).index(e) + 1 for e in effects]
                d_squared = sum((dr - er) ** 2 for dr, er in zip(dose_ranks, effect_ranks))
                rho = 1 - (6 * d_squared) / (n * (n**2 - 1)) if n > 1 else 0
                gradient_strength = abs(rho)
            else:
                gradient_strength = 0.0
                rho = 0.0

            if has_gradient and gradient_strength > 0.7:
                upgrade = 1
                direction = "increasing" if is_increasing else "decreasing"
                rationale = f"Clear dose-response gradient ({direction}, ρ={rho:.2f})"
            else:
                upgrade = 0
                rationale = f"No clear dose-response gradient detected (ρ={rho:.2f})"

            return UpgradeAssessment(
                domain="dose_response",
                upgrade=upgrade,
                applicable=True,
                rationale=rationale,
                details={
                    "n_dose_levels": n_doses,
                    "gradient_detected": has_gradient,
                    "correlation": rho,
                    "gradient_strength": gradient_strength,
                    "dose_effect_pairs": [
                        {"dose": d["dose"], "effect": d["effect"]}
                        for d in dose_data_sorted
                    ]
                }
            )

        return UpgradeAssessment(
            domain="dose_response",
            upgrade=0,
            applicable=False,
            rationale="Insufficient dose-response data for assessment",
            details={"n_dose_levels": n_doses}
        )

    def _assess_plausible_confounding(self, studies: list) -> UpgradeAssessment:
        """Assess plausible confounding upgrade domain.

        Per GRADE: When all plausible confounders would reduce the demonstrated
        effect (or increase it if no effect shown), this supports upgrading.

        This is primarily relevant for observational studies where:
        - Residual confounding would bias TOWARD null
        - Yet effect is still demonstrated
        """
        # Check study design - this domain is primarily for observational studies
        rct_count = sum(1 for s in studies if "random" in s.get("allocation", "").lower())
        total_studies = len(studies)

        if rct_count == total_studies:
            # All RCTs - confounding less relevant but can still be documented
            return UpgradeAssessment(
                domain="plausible_confounding",
                upgrade=0,
                applicable=False,
                rationale="All studies are RCTs; confounding assessment not applicable",
                details={
                    "study_design": "all_rcts",
                    "rct_count": rct_count,
                    "total_studies": total_studies
                }
            )

        # For observational studies, check for confounding indicators
        confounding_indicators = []
        healthy_user_bias = False
        indication_bias = False
        surveillance_bias = False

        for study in studies:
            adjustments = study.get("adjustments", [])
            confounders_noted = study.get("confounders", [])
            design = study.get("design", "").lower()

            if "propensity" in str(adjustments).lower():
                confounding_indicators.append("propensity_score_adjustment")
            if "instrumental" in str(design):
                confounding_indicators.append("instrumental_variable")
            if any("health" in c.lower() for c in confounders_noted):
                healthy_user_bias = True
            if any("indication" in c.lower() for c in confounders_noted):
                indication_bias = True

        # Determine if confounding would work against demonstrated effect
        # This typically requires domain expertise - we flag for review
        n_observational = total_studies - rct_count

        if n_observational > 0 and len(confounding_indicators) > 0:
            # Some adjustment for confounding was done
            upgrade = 0  # Conservative - requires expert review
            rationale = (f"Observational studies (n={n_observational}) with "
                        f"confounding adjustments: {', '.join(set(confounding_indicators))}. "
                        "Upgrade requires expert review of confounding direction.")
            applicable = True
        elif n_observational > 0:
            upgrade = 0
            rationale = f"Observational studies (n={n_observational}) without documented confounding adjustment"
            applicable = True
        else:
            upgrade = 0
            rationale = "Mixed design; confounding assessment indeterminate"
            applicable = False

        return UpgradeAssessment(
            domain="plausible_confounding",
            upgrade=upgrade,
            applicable=applicable,
            rationale=rationale,
            details={
                "rct_count": rct_count,
                "observational_count": n_observational,
                "total_studies": total_studies,
                "confounding_indicators": list(set(confounding_indicators)),
                "healthy_user_bias_noted": healthy_user_bias,
                "indication_bias_noted": indication_bias,
                "requires_expert_review": True if n_observational > 0 else False
            }
        )

    def _calculate_final_level(self, total_downgrade: int,
                                total_upgrade: int = 0) -> GradeLevel:
        """Calculate final GRADE level based on downgrades and upgrades.

        Per GRADE methodology:
        - Apply downgrades first
        - Then apply upgrades (observational only, or for documenting large effects)
        - Cannot upgrade RCTs above HIGH
        - Cannot upgrade observational studies above MODERATE
        - Maximum upgrade is +2 levels for observational studies

        Args:
            total_downgrade: Sum of downgrade levels (0-10)
            total_upgrade: Sum of upgrade levels (0-3)

        Returns:
            Final GRADE level
        """
        levels = [GradeLevel.HIGH, GradeLevel.MODERATE, GradeLevel.LOW, GradeLevel.VERY_LOW]

        if self.starting_level == "high":
            start_idx = 0
            # RCTs cannot be upgraded above HIGH
            max_upgrade = 0
        else:  # observational starts at LOW
            start_idx = 2
            # Observational can be upgraded up to MODERATE (but not HIGH)
            max_upgrade = min(total_upgrade, 2)

        # Apply downgrades first
        after_downgrade = min(start_idx + total_downgrade, 3)

        # Then apply upgrades (capped appropriately)
        # For observational: can go from VERY_LOW→LOW→MODERATE (max 2 levels up)
        # Cannot upgrade past MODERATE for observational studies
        if self.starting_level == "low" and max_upgrade > 0:
            # Calculate how far we can upgrade
            final_idx = max(after_downgrade - max_upgrade, 1)  # Cap at MODERATE (index 1)
        else:
            final_idx = after_downgrade

        return levels[final_idx]

    def _interpret_i2(self, i2: float) -> str:
        """Interpret I² value."""
        if i2 < 25:
            return "low"
        elif i2 < 50:
            return "moderate"
        elif i2 < 75:
            return "substantial"
        else:
            return "considerable"

    def _generate_summary(self, assessment: GradeAssessment) -> str:
        """Generate human-readable GRADE summary."""
        level_descriptions = {
            GradeLevel.HIGH: "We are very confident that the true effect lies close to the estimate",
            GradeLevel.MODERATE: "We are moderately confident; the true effect is likely close to the estimate but may be substantially different",
            GradeLevel.LOW: "Our confidence is limited; the true effect may be substantially different from the estimate",
            GradeLevel.VERY_LOW: "We have very little confidence; the true effect is likely substantially different from the estimate"
        }

        downgrades = [d for d in assessment.domains if d.downgrade > 0]
        downgrade_reasons = [f"{d.domain} ({d.rationale})" for d in downgrades]

        upgrades = [u for u in assessment.upgrades if u.upgrade > 0]
        upgrade_reasons = [f"{u.domain} ({u.rationale})" for u in upgrades]

        summary = f"GRADE: {assessment.final_level.value.upper()} certainty. "
        summary += level_descriptions[assessment.final_level] + ". "

        if downgrades:
            summary += f"Downgraded for: {'; '.join(downgrade_reasons)}. "
        else:
            summary += "No serious concerns across GRADE domains. "

        if upgrades:
            summary += f"Upgraded for: {'; '.join(upgrade_reasons)}."
        elif self.starting_level == "low":
            # Document when upgrades were assessed but not applied
            applicable_upgrades = [u for u in assessment.upgrades if u.applicable]
            if applicable_upgrades:
                summary += "Upgrade criteria assessed but not met."

        return summary
