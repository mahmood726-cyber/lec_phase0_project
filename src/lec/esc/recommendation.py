"""ESC Recommendation Class Derivation.

Derives ESC recommendation classes (I, IIa, IIb, III) and evidence levels (A, B, C)
based on evidence synthesis results and GRADE assessments.

Reference: ESC Guidelines for the diagnosis and management of chronic coronary
syndromes. Eur Heart J 2019;40:87-165

Classes of Recommendations:
- Class I:   Evidence/agreement that treatment is beneficial, useful, effective
             Wording: "Is recommended" / "Is indicated"
- Class IIa: Weight of evidence/opinion in favor of usefulness/efficacy
             Wording: "Should be considered"
- Class IIb: Usefulness/efficacy less well established
             Wording: "May be considered"
- Class III: Evidence/agreement that treatment is not useful/effective
             or may be harmful
             Wording: "Is not recommended"

Levels of Evidence:
- Level A: Data from multiple randomized clinical trials or meta-analyses
- Level B: Data from single randomized trial or large non-randomized studies
- Level C: Consensus of expert opinion and/or small studies, retrospective studies, registries
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum

from lec.core import utc_now_iso


class RecommendationClass(Enum):
    """ESC recommendation class."""
    CLASS_I = "I"
    CLASS_IIA = "IIa"
    CLASS_IIB = "IIb"
    CLASS_III = "III"
    CLASS_III_HARM = "III (harm)"
    CLASS_III_NO_BENEFIT = "III (no benefit)"


class EvidenceLevel(Enum):
    """ESC level of evidence."""
    LEVEL_A = "A"
    LEVEL_B = "B"
    LEVEL_C = "C"


# Standard ESC wording for each class
RECOMMENDATION_WORDING = {
    RecommendationClass.CLASS_I: "is recommended",
    RecommendationClass.CLASS_IIA: "should be considered",
    RecommendationClass.CLASS_IIB: "may be considered",
    RecommendationClass.CLASS_III: "is not recommended",
    RecommendationClass.CLASS_III_HARM: "is not recommended (potential harm)",
    RecommendationClass.CLASS_III_NO_BENEFIT: "is not recommended (no benefit)",
}


@dataclass
class ESCRecommendation:
    """ESC-compliant recommendation for a clinical question."""
    intervention: str
    population: str
    recommendation_class: RecommendationClass
    evidence_level: EvidenceLevel
    recommendation_text: str
    supporting_evidence: dict = field(default_factory=dict)
    rationale: str = ""
    considerations: List[str] = field(default_factory=list)
    safety_considerations: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "intervention": self.intervention,
            "population": self.population,
            "class": self.recommendation_class.value,
            "level": self.evidence_level.value,
            "text": self.recommendation_text,
            "supporting_evidence": self.supporting_evidence,
            "rationale": self.rationale,
            "considerations": self.considerations,
            "safety_considerations": self.safety_considerations,
            "created_at": self.created_at
        }

    def to_guideline_format(self) -> str:
        """Format as ESC guideline box."""
        class_color = {
            RecommendationClass.CLASS_I: "green",
            RecommendationClass.CLASS_IIA: "yellow",
            RecommendationClass.CLASS_IIB: "orange",
            RecommendationClass.CLASS_III: "red",
            RecommendationClass.CLASS_III_HARM: "red",
            RecommendationClass.CLASS_III_NO_BENEFIT: "red"
        }

        lines = [
            f"Recommendation: Class {self.recommendation_class.value}, Level {self.evidence_level.value}",
            "-" * 60,
            f"{self.recommendation_text}",
            "",
            f"Rationale: {self.rationale}",
        ]

        if self.considerations:
            lines.append("")
            lines.append("Considerations:")
            for c in self.considerations:
                lines.append(f"  - {c}")

        if self.safety_considerations:
            lines.append("")
            lines.append("Safety:")
            for s in self.safety_considerations:
                lines.append(f"  - {s}")

        return "\n".join(lines)


class RecommendationDeriver:
    """Derives ESC recommendations from evidence synthesis."""

    # Thresholds for classification
    EFFECT_THRESHOLDS = {
        "strong_benefit": 0.75,  # HR/RR < 0.75 = 25% relative reduction
        "moderate_benefit": 0.88,  # HR/RR < 0.88 = 12% relative reduction
        "no_effect_lower": 0.97,
        "no_effect_upper": 1.03,
        "harm": 1.05  # HR/RR > 1.05 = potential harm
    }

    def __init__(self, lec_object: dict):
        """Initialize with LEC object.

        Args:
            lec_object: Complete LEC object with analysis and GRADE
        """
        self.lec = lec_object
        self.question = lec_object.get("question", {})
        self.analysis = lec_object.get("analysis", {})
        self.grade = lec_object.get("grade_assessment")

    def derive(self) -> ESCRecommendation:
        """Derive ESC recommendation from evidence.

        Returns:
            ESCRecommendation object
        """
        # Get PICO components
        pico = self.question.get("pico", {})
        intervention = pico.get("intervention", "Intervention")
        population = pico.get("population", "Target population")

        # Get effect estimate and certainty
        results = self.analysis.get("results", {})
        pooled = results.get("pooled", {})
        effect = pooled.get("estimate", 1.0)
        ci_low = pooled.get("ci_low", 0.5)
        ci_high = pooled.get("ci_high", 2.0)

        # Get certainty level
        certainty = self._get_certainty_level()

        # Get evidence level
        evidence_level = self._determine_evidence_level()

        # Check for safety concerns
        safety_concerns = self._assess_safety_concerns()

        # Derive recommendation class
        rec_class, rationale = self._derive_class(
            effect=effect,
            ci_low=ci_low,
            ci_high=ci_high,
            certainty=certainty,
            safety_concerns=safety_concerns
        )

        # Generate recommendation text
        rec_text = self._generate_recommendation_text(
            intervention=intervention,
            population=population,
            rec_class=rec_class
        )

        # Compile considerations
        considerations = self._compile_considerations(
            effect=effect,
            ci_low=ci_low,
            ci_high=ci_high,
            certainty=certainty
        )

        return ESCRecommendation(
            intervention=intervention,
            population=population,
            recommendation_class=rec_class,
            evidence_level=evidence_level,
            recommendation_text=rec_text,
            supporting_evidence={
                "effect_estimate": effect,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "certainty": certainty,
                "n_studies": self.lec.get("included_studies", {}).get("count", 0)
            },
            rationale=rationale,
            considerations=considerations,
            safety_considerations=safety_concerns
        )

    def _get_certainty_level(self) -> str:
        """Get GRADE certainty level."""
        if self.grade:
            return self.grade.get("final_level", "moderate")

        # Infer from analysis
        results = self.analysis.get("results", {})
        i2 = results.get("heterogeneity", {}).get("i2", 0)
        n_studies = self.lec.get("included_studies", {}).get("count", 0)

        if n_studies >= 3 and i2 < 50:
            return "moderate"
        elif n_studies >= 2:
            return "low"
        else:
            return "very_low"

    def _determine_evidence_level(self) -> EvidenceLevel:
        """Determine ESC evidence level.

        Level A: Multiple RCTs or meta-analysis of RCTs
        Level B: Single RCT or large non-randomized studies
        Level C: Expert consensus, small studies, registries
        """
        n_studies = self.lec.get("included_studies", {}).get("count", 0)
        study_design = self.analysis.get("model", {}).get("design", "rct")

        if n_studies >= 2 and study_design == "rct":
            return EvidenceLevel.LEVEL_A
        elif n_studies >= 1 and study_design == "rct":
            return EvidenceLevel.LEVEL_B
        else:
            return EvidenceLevel.LEVEL_C

    def _assess_safety_concerns(self) -> List[str]:
        """Assess safety concerns from evidence."""
        concerns = []

        # Check for safety outcomes in analysis
        safety_data = self.analysis.get("safety_outcomes", [])
        for safety in safety_data:
            if safety.get("safety_signal"):
                concerns.append(f"{safety.get('name', 'Safety signal')}: requires monitoring")

        # Check extraction data for safety signals
        # Would load from extended_extraction.json in production

        return concerns

    def _derive_class(self, effect: float, ci_low: float, ci_high: float,
                      certainty: str, safety_concerns: List[str]) -> tuple:
        """Derive recommendation class based on evidence.

        Decision logic:
        1. Check for harm first (Class III)
        2. Check certainty and effect magnitude
        3. Consider safety concerns

        Returns:
            Tuple of (RecommendationClass, rationale)
        """
        # Check for harm signal
        if effect > self.EFFECT_THRESHOLDS["harm"] and ci_low > 1.0:
            return (
                RecommendationClass.CLASS_III_HARM,
                f"Effect estimate {effect:.2f} with CI entirely above 1.0 suggests potential harm"
            )

        # Check for no effect
        crosses_null = ci_low < 1.0 < ci_high
        if crosses_null and self.EFFECT_THRESHOLDS["no_effect_lower"] < effect < self.EFFECT_THRESHOLDS["no_effect_upper"]:
            return (
                RecommendationClass.CLASS_III_NO_BENEFIT,
                f"Effect estimate {effect:.2f} with CI crossing null suggests no meaningful benefit"
            )

        # Check effect magnitude and certainty for benefit
        significant_benefit = ci_high < 1.0  # CI entirely below null

        # Benefit with High Certainty -> Class I (Standard ESC logic)
        if significant_benefit and certainty == "high":
            if safety_concerns:
                return (
                    RecommendationClass.CLASS_IIA,
                    f"Significant benefit (HR {effect:.2f}) with high certainty, but safety considerations require monitoring"
                )
            return (
                RecommendationClass.CLASS_I,
                f"Significant, consistent benefit demonstrated (HR {effect:.2f}, CI {ci_low:.2f}-{ci_high:.2f}) with high certainty"
            )

        # Benefit with Moderate Certainty -> Class I or IIa
        if significant_benefit and certainty == "moderate":
            if effect < self.EFFECT_THRESHOLDS["strong_benefit"]:
                return (
                    RecommendationClass.CLASS_I,
                    f"Strong benefit (HR {effect:.2f}) with moderate certainty"
                )
            else:
                return (
                    RecommendationClass.CLASS_IIA,
                    f"Moderate benefit (HR {effect:.2f}) with moderate certainty"
                )

        # Moderate benefit with Low Certainty -> Class IIa
        if significant_benefit and effect < self.EFFECT_THRESHOLDS["moderate_benefit"]:
            return (
                RecommendationClass.CLASS_IIA,
                f"Benefit demonstrated (HR {effect:.2f}) but limited certainty ({certainty})"
            )

        # Smaller benefit or CI crosses null
        if effect < 1.0:
            if certainty in ["high", "moderate"]:
                return (
                    RecommendationClass.CLASS_IIB,
                    f"Potential benefit (HR {effect:.2f}) but CI crosses null ({ci_low:.2f}-{ci_high:.2f}) or effect is small"
                )
            else:
                return (
                    RecommendationClass.CLASS_IIB,
                    f"Uncertain benefit (HR {effect:.2f}) with {certainty} certainty"
                )

        # Default for uncertain situations
        return (
            RecommendationClass.CLASS_IIB,
            f"Uncertain benefit-harm balance based on available evidence"
        )

    def _generate_recommendation_text(self, intervention: str, population: str,
                                       rec_class: RecommendationClass) -> str:
        """Generate standard ESC recommendation text."""
        wording = RECOMMENDATION_WORDING[rec_class]

        # Clean up intervention name
        intervention_clean = intervention.replace("_", " ")

        return f"{intervention_clean} {wording} in {population.lower()}"

    def _compile_considerations(self, effect: float, ci_low: float,
                                 ci_high: float, certainty: str) -> List[str]:
        """Compile clinical considerations."""
        considerations = []

        # Effect magnitude
        if effect < 0.70:
            considerations.append(f"Large relative risk reduction ({(1-effect)*100:.0f}%)")
        elif effect < 0.85:
            considerations.append(f"Moderate relative risk reduction ({(1-effect)*100:.0f}%)")

        # Certainty
        if certainty == "high":
            considerations.append("High certainty evidence from multiple well-conducted RCTs")
        elif certainty == "moderate":
            considerations.append("Moderate certainty; true effect likely close to estimate")
        elif certainty == "low":
            considerations.append("Low certainty; true effect may differ substantially")
        else:
            considerations.append("Very low certainty; estimate is uncertain")

        # CI width
        ci_width = ci_high - ci_low
        if ci_width > 0.5:
            considerations.append("Wide confidence interval indicates imprecision")

        # Heterogeneity
        heterogeneity = self.analysis.get("results", {}).get("heterogeneity", {})
        i2 = heterogeneity.get("i2", 0)
        if i2 > 50:
            considerations.append(f"Substantial heterogeneity (I²={i2:.0f}%) suggests variable effects")

        return considerations


def derive_recommendation(lec_object: dict) -> ESCRecommendation:
    """Convenience function to derive ESC recommendation.

    Args:
        lec_object: Complete LEC object

    Returns:
        ESCRecommendation object
    """
    deriver = RecommendationDeriver(lec_object)
    return deriver.derive()


def format_recommendation_box(recommendation: ESCRecommendation) -> str:
    """Format recommendation as ESC-style colored box (markdown).

    Args:
        recommendation: ESCRecommendation object

    Returns:
        Markdown formatted recommendation box
    """
    class_colors = {
        "I": "#008000",      # Green
        "IIa": "#FFA500",    # Orange
        "IIb": "#FFD700",    # Gold
        "III": "#FF0000",    # Red
    }

    rec_class = recommendation.recommendation_class.value
    base_class = rec_class.split()[0]  # Handle "III (harm)" etc.
    color = class_colors.get(base_class, "#808080")

    lines = [
        f"### Recommendation",
        f"**Class {rec_class} | Level {recommendation.evidence_level.value}**",
        "",
        f"> {recommendation.recommendation_text}",
        "",
        f"**Rationale:** {recommendation.rationale}",
    ]

    if recommendation.considerations:
        lines.extend([
            "",
            "**Considerations:**",
        ])
        for c in recommendation.considerations:
            lines.append(f"- {c}")

    if recommendation.safety_considerations:
        lines.extend([
            "",
            "**Safety:**",
        ])
        for s in recommendation.safety_considerations:
            lines.append(f"- {s}")

    return "\n".join(lines)
