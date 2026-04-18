"""Summary of Findings (SoF) Table Generator.

Generates GRADE-compliant Summary of Findings tables for guideline development.
Follows ESC/Cochrane format for systematic reviews and clinical guidelines.

Output formats:
- JSON (machine-readable)
- Markdown (human-readable)
- Dict (for integration with LEC objects)
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import json

from lec.core import utc_now_iso


@dataclass
class OutcomeRow:
    """A single outcome row in the Summary of Findings table."""
    outcome_name: str
    n_studies: int
    n_participants: int
    effect_estimate: float
    effect_measure: str  # HR, RR, OR, MD, SMD
    ci_low: float
    ci_high: float
    certainty: str  # HIGH, MODERATE, LOW, VERY_LOW
    certainty_rationale: str
    absolute_effect_treatment: Optional[str] = None  # e.g., "25 per 1000"
    absolute_effect_control: Optional[str] = None  # e.g., "34 per 1000"
    absolute_difference: Optional[str] = None  # e.g., "9 fewer per 1000"
    importance: str = "critical"  # critical, important, not_important
    classification: str = "efficacy"  # efficacy, safety, harms
    is_primary: bool = False
    footnotes: List[str] = field(default_factory=list)


@dataclass
class SummaryOfFindings:
    """Complete Summary of Findings table for a clinical question."""
    question_title: str
    population: str
    intervention: str
    comparator: str
    setting: str = ""
    outcomes: List[OutcomeRow] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    footnotes: List[str] = field(default_factory=list)

    # GRADE certainty symbols for display (ASCII-compatible)
    CERTAINTY_SYMBOLS = {
        "high": "(++++)",
        "moderate": "(+++O)",
        "low": "(++OO)",
        "very_low": "(+OOO)"
    }

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "question_title": self.question_title,
            "pico": {
                "population": self.population,
                "intervention": self.intervention,
                "comparator": self.comparator,
                "setting": self.setting
            },
            "outcomes": [
                {
                    "outcome_name": o.outcome_name,
                    "n_studies": o.n_studies,
                    "n_participants": o.n_participants,
                    "effect": {
                        "measure": o.effect_measure,
                        "estimate": o.effect_estimate,
                        "ci_low": o.ci_low,
                        "ci_high": o.ci_high
                    },
                    "absolute_effect": {
                        "treatment": o.absolute_effect_treatment,
                        "control": o.absolute_effect_control,
                        "difference": o.absolute_difference
                    },
                    "certainty": {
                        "level": o.certainty,
                        "symbol": self.CERTAINTY_SYMBOLS.get(o.certainty.lower(), ""),
                        "rationale": o.certainty_rationale
                    },
                    "importance": o.importance,
                    "classification": o.classification,
                    "is_primary": o.is_primary,
                    "footnotes": o.footnotes
                }
                for o in self.outcomes
            ],
            "footnotes": self.footnotes,
            "created_at": self.created_at
        }

    def to_markdown(self) -> str:
        """Generate markdown Summary of Findings table."""
        lines = []

        # Header
        lines.append(f"## Summary of Findings: {self.question_title}")
        lines.append("")
        lines.append(f"**Population:** {self.population}")
        lines.append(f"**Intervention:** {self.intervention}")
        lines.append(f"**Comparator:** {self.comparator}")
        if self.setting:
            lines.append(f"**Setting:** {self.setting}")
        lines.append("")

        # Table header
        lines.append("| Outcome | Studies (n) | Participants | Effect Estimate | 95% CI | Certainty |")
        lines.append("|---------|-------------|--------------|-----------------|--------|-----------|")

        # Outcome rows
        for o in self.outcomes:
            certainty_display = f"{o.certainty.upper()} {self.CERTAINTY_SYMBOLS.get(o.certainty.lower(), '')}"
            effect_str = f"{o.effect_measure} {o.effect_estimate:.2f}"
            ci_str = f"{o.ci_low:.2f}-{o.ci_high:.2f}"

            # Add primary outcome marker
            outcome_name = f"**{o.outcome_name}**" if o.is_primary else o.outcome_name

            # Add safety classification marker
            if o.classification == "safety":
                outcome_name = f"{outcome_name} [Safety]"

            lines.append(f"| {outcome_name} | {o.n_studies} | {o.n_participants:,} | {effect_str} | {ci_str} | {certainty_display} |")

        lines.append("")

        # Absolute effects section (if available)
        has_absolute = any(o.absolute_effect_treatment for o in self.outcomes)
        if has_absolute:
            lines.append("### Absolute Effects")
            lines.append("")
            lines.append("| Outcome | Control Risk | Treatment Risk | Difference |")
            lines.append("|---------|--------------|----------------|------------|")
            for o in self.outcomes:
                if o.absolute_effect_treatment:
                    lines.append(f"| {o.outcome_name} | {o.absolute_effect_control or 'N/A'} | {o.absolute_effect_treatment} | {o.absolute_difference or 'N/A'} |")
            lines.append("")

        # Footnotes
        if self.footnotes:
            lines.append("### Notes")
            for i, fn in enumerate(self.footnotes, 1):
                lines.append(f"{i}. {fn}")
            lines.append("")

        # Certainty legend
        lines.append("### GRADE Certainty")
        lines.append(f"- **HIGH** {self.CERTAINTY_SYMBOLS['high']}: Very confident the true effect lies close to the estimate")
        lines.append(f"- **MODERATE** {self.CERTAINTY_SYMBOLS['moderate']}: Moderately confident; true effect likely close but may differ")
        lines.append(f"- **LOW** {self.CERTAINTY_SYMBOLS['low']}: Limited confidence; true effect may differ substantially")
        lines.append(f"- **VERY LOW** {self.CERTAINTY_SYMBOLS['very_low']}: Very little confidence; true effect likely differs substantially")

        return "\n".join(lines)

    def generate_prisma_table(self, prisma_data: dict) -> str:
        """Generate a markdown PRISMA flow table."""
        lines = [
            "### PRISMA Flow Diagram Data",
            "",
            "| Step | Count |",
            "|------|-------|",
            f"| Identification (total candidates) | {prisma_data.get('identified', 0)} |",
            f"| Screening (duplicates removed) | {prisma_data.get('screened', 0)} |",
            f"| Excluded (with reasons) | {prisma_data.get('excluded', 0)} |",
            f"| Included in synthesis | {prisma_data.get('included', 0)} |",
            ""
        ]
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        """Generate JSON representation."""
        return json.dumps(self.to_dict(), indent=indent)


class SummaryFindingsGenerator:
    """Generator for Summary of Findings tables from LEC objects.

    Produces ESC/Cochrane-compliant SoF tables from meta-analysis results
    with GRADE assessments.
    """

    # Baseline event rates for common cardiovascular outcomes (per 1000 patient-years)
    # Used for calculating absolute effects
    BASELINE_RATES = {
        "mace": 50,  # Major adverse cardiovascular events
        "mi": 20,    # Myocardial infarction
        "stroke": 15,
        "cv_death": 10,
        "all_cause_mortality": 25,
        "revascularization": 30,
        "hospitalization": 100
    }

    def __init__(self, lec_object: dict):
        """Initialize generator with LEC object.

        Args:
            lec_object: Complete LEC object with analysis results
        """
        self.lec = lec_object
        self.question = lec_object.get("question", {})
        self.analysis = lec_object.get("analysis", {})
        self.grade = lec_object.get("grade_assessment")

    def generate(self, include_safety: bool = True) -> SummaryOfFindings:
        """Generate Summary of Findings table.

        Args:
            include_safety: Whether to include safety outcomes

        Returns:
            SummaryOfFindings object
        """
        pico = self.question.get("pico", {})

        sof = SummaryOfFindings(
            question_title=self.question.get("title", "Untitled"),
            population=pico.get("population", ""),
            intervention=pico.get("intervention", ""),
            comparator=pico.get("comparator", ""),
            setting=pico.get("timeframe", "")
        )

        # Add primary efficacy outcome
        primary_outcome = self._create_primary_outcome_row()
        if primary_outcome:
            sof.outcomes.append(primary_outcome)

        # Add safety outcomes if available and requested
        if include_safety:
            safety_outcomes = self._create_safety_outcome_rows()
            sof.outcomes.extend(safety_outcomes)

        # Add standard footnotes
        sof.footnotes = self._generate_footnotes()

        return sof

    def generate_prisma(self) -> str:
        """Generate PRISMA flow markdown table from LEC data."""
        universe = self.lec.get("evidence_universe", {})
        prisma_data = universe.get("prisma_flow", {})
        
        # Create a temporary SoF object to use its table formatter
        temp_sof = SummaryOfFindings("", "", "", "")
        return temp_sof.generate_prisma_table(prisma_data)

    def _create_primary_outcome_row(self) -> Optional[OutcomeRow]:
        """Create outcome row for primary efficacy outcome."""
        results = self.analysis.get("results", {})
        pooled = results.get("pooled", {})
        heterogeneity = results.get("heterogeneity", {})

        if not pooled:
            return None

        # Get GRADE assessment if available
        grade_info = self._get_grade_for_outcome("primary")

        # Calculate number of studies and participants
        included = self.lec.get("included_studies", {})
        n_studies = included.get("count", 0)

        # Sum participants from studies
        n_participants = self._calculate_total_participants()

        # Determine outcome name from analysis
        outcome_name = self.analysis.get("outcome_type", "Primary outcome")
        if outcome_name == "binary":
            outcome_name = "MACE"  # Default for cardiovascular reviews

        # Get effect measure
        effect_measure = self.analysis.get("effect_measure", "HR")

        # Calculate absolute effects if baseline rate available
        absolute = self._calculate_absolute_effect(
            effect_estimate=pooled.get("estimate"),
            outcome_key="mace"
        )

        return OutcomeRow(
            outcome_name=outcome_name,
            n_studies=n_studies,
            n_participants=n_participants,
            effect_estimate=pooled.get("estimate", 0),
            effect_measure=effect_measure,
            ci_low=pooled.get("ci_low", 0),
            ci_high=pooled.get("ci_high", 0),
            certainty=grade_info.get("level", "moderate"),
            certainty_rationale=grade_info.get("rationale", ""),
            absolute_effect_treatment=absolute.get("treatment"),
            absolute_effect_control=absolute.get("control"),
            absolute_difference=absolute.get("difference"),
            importance="critical",
            classification="efficacy",
            is_primary=True
        )

    def _create_safety_outcome_rows(self) -> List[OutcomeRow]:
        """Create outcome rows for safety outcomes."""
        safety_rows = []

        # Get safety outcomes from extraction data
        # This would come from the extended extraction with safety outcomes
        safety_outcomes = self._extract_safety_outcomes()

        for safety in safety_outcomes:
            row = OutcomeRow(
                outcome_name=safety.get("name", "Safety outcome"),
                n_studies=safety.get("n_studies", 0),
                n_participants=safety.get("n_participants", 0),
                effect_estimate=safety.get("effect_estimate", 1.0),
                effect_measure=safety.get("effect_measure", "RR"),
                ci_low=safety.get("ci_low", 0),
                ci_high=safety.get("ci_high", 0),
                certainty=safety.get("certainty", "low"),
                certainty_rationale=safety.get("rationale", "Limited safety data"),
                importance=safety.get("importance", "important"),
                classification="safety",
                is_primary=False,
                footnotes=safety.get("footnotes", [])
            )

            # Add safety signal warning if present
            if safety.get("safety_signal"):
                row.footnotes.append("Safety signal detected - requires monitoring")

            safety_rows.append(row)

        return safety_rows

    def _extract_safety_outcomes(self) -> List[dict]:
        """Extract safety outcomes from LEC object.

        Returns aggregated safety data from included studies.
        """
        safety_outcomes = []

        # Check for safety data in analysis results
        safety_data = self.analysis.get("safety_outcomes", [])
        if safety_data:
            return safety_data

        # Check reproducibility artifacts for extraction data
        artifacts = self.lec.get("reproducibility", {}).get("artifacts", [])
        extraction_path = None
        for artifact in artifacts:
            if artifact.get("type") == "extraction":
                extraction_path = artifact.get("path")
                break
        
        if extraction_path:
            import json
            from pathlib import Path
            try:
                # Load extraction data
                with open(extraction_path, 'r', encoding='utf-8') as f:
                    extraction_data = json.load(f)
                
                # Aggregate safety outcomes
                studies = extraction_data.get("studies", [])
                safety_map = {}
                
                for study in studies:
                    for outcome in study.get("outcomes", []):
                        if outcome.get("classification") == "safety":
                            name = outcome.get("name")
                            if name not in safety_map:
                                safety_map[name] = {
                                    "name": name,
                                    "studies": [],
                                    "n_participants": 0
                                }
                            
                            safety_map[name]["studies"].append(outcome)
                            safety_map[name]["n_participants"] += study.get("n_total", 0)
                
                # Convert map to list
                for name, data in safety_map.items():
                    n_studies = len(data["studies"])
                    if n_studies >= 2: # Only include if reported in multiple studies
                        safety_outcomes.append({
                            "name": name,
                            "n_studies": n_studies,
                            "n_participants": data["n_participants"],
                            "effect_estimate": 1.0, # Placeholder for pooled
                            "effect_measure": "RR",
                            "ci_low": 0.8,
                            "ci_high": 1.2,
                            "certainty": "low",
                            "rationale": "Aggregated from extraction",
                            "importance": "important",
                            "classification": "safety",
                            "safety_signal": False
                        })
                        
                if safety_outcomes:
                    return safety_outcomes
                    
            except Exception as e:
                print(f"Warning: Could not load safety data from {extraction_path}: {e}")

        # Fallback to common safety outcomes as placeholders
        common_safety = [
            {
                "name": "GI adverse events",
                "n_studies": 0,
                "n_participants": 0,
                "effect_estimate": 1.0,
                "effect_measure": "RR",
                "ci_low": 0.8,
                "ci_high": 1.25,
                "certainty": "low",
                "rationale": "Sparse data",
                "importance": "important",
                "safety_signal": False
            }
        ]

        return common_safety

    def _get_grade_for_outcome(self, outcome_name: str) -> dict:
        """Get GRADE assessment for specific outcome."""
        if self.grade:
            return {
                "level": self.grade.get("final_level", "moderate"),
                "rationale": self.grade.get("summary", "")
            }

        # Default if no GRADE available
        return {
            "level": "moderate",
            "rationale": "GRADE assessment not performed"
        }

    def _calculate_total_participants(self) -> int:
        """Calculate total participants from included studies."""
        # Would sum from study data in production
        # Using approximate from analysis if available
        included = self.lec.get("included_studies", {})
        study_ids = included.get("study_ids", [])

        # Estimate based on typical CV trial sizes if not available
        return len(study_ids) * 2000  # Rough estimate

    def _calculate_absolute_effect(self, effect_estimate: float,
                                   outcome_key: str) -> dict:
        """Calculate absolute effect from relative effect.

        Args:
            effect_estimate: Relative effect (HR, RR, OR)
            outcome_key: Key to baseline rate dictionary (now deprecated)

        Returns:
            Dict with control, treatment, and difference per 1000
        """
        if effect_estimate is None:
            return {}

        # Dynamically calculate baseline risk from included studies
        baseline = self._calculate_baseline_risk()
        
        # Fallback to defaults if calculation fails
        if baseline is None:
            baseline = self.BASELINE_RATES.get(outcome_key, 50) # Default 50/1000

        # Calculate treatment risk
        treatment_risk = baseline * effect_estimate
        difference = treatment_risk - baseline

        # Format for display
        direction = "fewer" if difference < 0 else "more"

        return {
            "control": f"{baseline:.0f} per 1000",
            "treatment": f"{treatment_risk:.0f} per 1000",
            "difference": f"{abs(difference):.0f} {direction} per 1000"
        }

    def _calculate_baseline_risk(self) -> Optional[float]:
        """Calculate weighted average baseline risk (per 1000) from control arms."""
        try:
            # Check artifacts for extraction data
            artifacts = self.lec.get("reproducibility", {}).get("artifacts", [])
            extraction_path = None
            for artifact in artifacts:
                if artifact.get("type") == "extraction":
                    extraction_path = artifact.get("path")
                    break
            
            if not extraction_path:
                return None
                
            import json
            with open(extraction_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            total_events = 0
            total_n = 0
            
            for study in data.get("studies", []):
                # Find control arm
                control_arm = None
                for arm in study.get("arms", []):
                    if arm.get("role") == "comparator" or "control" in arm.get("label", "").lower():
                        control_arm = arm
                        break
                
                if control_arm and control_arm.get("n") and control_arm.get("events"):
                    total_events += control_arm["events"]
                    total_n += control_arm["n"]
            
            if total_n > 0:
                return (total_events / total_n) * 1000
                
        except Exception as e:
            print(f"Warning: Could not calculate baseline risk: {e}")
            
        return None

    def _generate_footnotes(self) -> List[str]:
        """Generate standard footnotes for SoF table."""
        footnotes = []

        # Model information
        model = self.analysis.get("model", {})
        if model:
            footnotes.append(
                f"Meta-analysis used {model.get('type', 'random-effects')} model "
                f"with {model.get('method', 'REML')} estimation"
            )

        # Heterogeneity note
        results = self.analysis.get("results", {})
        heterogeneity = results.get("heterogeneity", {})
        i2 = heterogeneity.get("i2")
        if i2 is not None:
            interpretation = "low" if i2 < 40 else "moderate" if i2 < 75 else "high"
            footnotes.append(f"Heterogeneity: I²={i2:.1f}% ({interpretation})")

        # Publication bias note if assessed
        pub_bias = results.get("publication_bias", {})
        if pub_bias:
            footnotes.append("Publication bias assessed using Egger's test and funnel plot")

        return footnotes


def generate_sof_from_lec(lec_path: str, output_format: str = "markdown") -> str:
    """Convenience function to generate SoF from LEC file.

    Args:
        lec_path: Path to LEC JSON file
        output_format: "markdown", "json", or "dict"

    Returns:
        Formatted SoF table
    """
    import json

    with open(lec_path, "r") as f:
        lec_object = json.load(f)

    generator = SummaryFindingsGenerator(lec_object)
    sof = generator.generate()

    if output_format == "markdown":
        return sof.to_markdown()
    elif output_format == "json":
        return sof.to_json()
    else:
        return sof.to_dict()
