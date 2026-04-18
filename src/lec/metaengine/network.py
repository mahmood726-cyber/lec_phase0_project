"""Network Meta-Analysis (NMA) Support.

Provides data structures and utilities for network meta-analysis compatibility.
Full NMA computation would be handled by external engines (netmeta, gemtc).

METHODOLOGICAL NOTE (RSM Editorial Fix):
-----------------------------------------
The pooling methods in this module use NAIVE POOLING for demonstration purposes:
    pooled_log = sum(log_estimates) / len(log_estimates)

This is NOT suitable for production NMA. Production implementations should use:
1. Consistency models (Lu-Ades framework)
2. Node-splitting for inconsistency detection
3. Proper network geometry assessment
4. Surface Under Cumulative Ranking (SUCRA) for treatment rankings

For rigorous NMA, export data to R netmeta or OpenBUGS/JAGS via gemtc.
The prepare_netmeta_input() function generates R-ready data structures.

References:
- Salanti G. Indirect and mixed-treatment comparison. Lancet 2012;379:706-16
- Dias S et al. Network meta-analysis for decision-making. Wiley 2018
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
import math

from lec.core import utc_now_iso, sha256_string, get_logger

logger = get_logger("network")


@dataclass
class Treatment:
    """Treatment/intervention in the network."""
    id: str
    name: str
    category: Optional[str] = None  # e.g., "anti-inflammatory", "statin"


@dataclass
class Comparison:
    """Direct comparison between two treatments."""
    treatment_a: str
    treatment_b: str
    n_studies: int
    effect_estimate: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    i2: Optional[float] = None


@dataclass
class NetworkData:
    """Data structure for network meta-analysis."""
    topic: str
    treatments: List[Treatment]
    comparisons: List[Comparison]
    reference_treatment: str
    outcome_type: str  # binary, continuous, time_to_event
    effect_measure: str  # OR, RR, HR, MD, SMD
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "treatments": [{"id": t.id, "name": t.name, "category": t.category}
                           for t in self.treatments],
            "comparisons": [
                {
                    "treatment_a": c.treatment_a,
                    "treatment_b": c.treatment_b,
                    "n_studies": c.n_studies,
                    "effect_estimate": c.effect_estimate,
                    "ci_low": c.ci_low,
                    "ci_high": c.ci_high,
                    "i2": c.i2
                }
                for c in self.comparisons
            ],
            "reference_treatment": self.reference_treatment,
            "outcome_type": self.outcome_type,
            "effect_measure": self.effect_measure,
            "created_at": self.created_at,
            "network_hash": self.network_hash()
        }

    def network_hash(self) -> str:
        """Generate hash of network structure."""
        treatments_str = ",".join(sorted(t.id for t in self.treatments))
        comparisons_str = ",".join(
            sorted(f"{c.treatment_a}-{c.treatment_b}" for c in self.comparisons)
        )
        return sha256_string(f"{treatments_str}|{comparisons_str}")[:16]


class NetworkBuilder:
    """Builds network meta-analysis data from pairwise studies."""

    def __init__(self, topic: str, reference_treatment: str = "placebo"):
        self.topic = topic
        self.reference = reference_treatment
        self.treatments: Dict[str, Treatment] = {}
        self.studies: List[dict] = []

    def add_treatment(self, id: str, name: str,
                      category: Optional[str] = None) -> "NetworkBuilder":
        """Add treatment to network."""
        self.treatments[id] = Treatment(id=id, name=name, category=category)
        return self

    def add_study(self, study_id: str, treatment_a: str, treatment_b: str,
                  estimate: float, ci_low: float, ci_high: float,
                  n_a: int, n_b: int, events_a: int = None,
                  events_b: int = None) -> "NetworkBuilder":
        """Add study to network."""
        # Auto-add treatments if not present
        if treatment_a not in self.treatments:
            self.treatments[treatment_a] = Treatment(id=treatment_a, name=treatment_a)
        if treatment_b not in self.treatments:
            self.treatments[treatment_b] = Treatment(id=treatment_b, name=treatment_b)

        self.studies.append({
            "study_id": study_id,
            "treatment_a": treatment_a,
            "treatment_b": treatment_b,
            "estimate": estimate,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "n_a": n_a,
            "n_b": n_b,
            "events_a": events_a,
            "events_b": events_b
        })
        return self

    def add_studies_from_extraction(self, extraction_data: dict) -> "NetworkBuilder":
        """Add studies from LEC extraction data."""
        for study in extraction_data.get("studies", []):
            arms = study.get("arms", [])
            if len(arms) < 2:
                continue

            # Identify treatment and comparator
            treatment_arm = next((a for a in arms if a.get("role") == "intervention"), arms[0])
            control_arm = next((a for a in arms if a.get("role") == "comparator"), arms[1])

            treatment_id = treatment_arm.get("label", "treatment")
            control_id = control_arm.get("label", "control")

            # Get effect from first outcome
            outcomes = study.get("outcomes", [])
            if outcomes:
                effect = outcomes[0].get("effect", {})
                estimate = effect.get("estimate")
                ci_low = effect.get("ci_low")
                ci_high = effect.get("ci_high")

                if estimate and ci_low and ci_high:
                    self.add_study(
                        study_id=study.get("study_id"),
                        treatment_a=treatment_id,
                        treatment_b=control_id,
                        estimate=estimate,
                        ci_low=ci_low,
                        ci_high=ci_high,
                        n_a=treatment_arm.get("n", 0),
                        n_b=control_arm.get("n", 0),
                        events_a=treatment_arm.get("events"),
                        events_b=control_arm.get("events")
                    )

        return self

    def build(self, outcome_type: str = "binary",
              effect_measure: str = "OR") -> NetworkData:
        """Build network data structure."""
        # Aggregate comparisons
        comparison_key = lambda s: tuple(sorted([s["treatment_a"], s["treatment_b"]]))
        comparison_groups: Dict[Tuple, List[dict]] = {}

        for study in self.studies:
            key = comparison_key(study)
            if key not in comparison_groups:
                comparison_groups[key] = []
            comparison_groups[key].append(study)

        comparisons = []
        for (t_a, t_b), studies in comparison_groups.items():
            # Simple pooling for direct comparison
            n_studies = len(studies)

            if n_studies == 1:
                s = studies[0]
                estimate = s["estimate"]
                ci_low = s["ci_low"]
                ci_high = s["ci_high"]
                i2 = 0
            else:
                # NAIVE POOLING - FOR DEMONSTRATION ONLY
                # Production NMA should use consistency models (Lu-Ades)
                # with proper variance weighting and inconsistency checks.
                # See prepare_netmeta_input() for R netmeta-ready export.
                log_estimates = []
                for s in studies:
                    if s["estimate"] > 0:
                        log_estimates.append(math.log(s["estimate"]))
                    else:
                        logger.warning(f"Skipping study {s.get('study_id')} in network pooling: invalid estimate {s['estimate']}")
                
                if log_estimates:
                    pooled_log = sum(log_estimates) / len(log_estimates)
                    estimate = math.exp(pooled_log)
                    # Approximate CI from individual studies (conservative)
                    ci_low = min(s["ci_low"] for s in studies)
                    ci_high = max(s["ci_high"] for s in studies)
                    i2 = 0  # Proper I² requires variance-weighted pooling
                else:
                    continue

            comparisons.append(Comparison(
                treatment_a=t_a,
                treatment_b=t_b,
                n_studies=n_studies,
                effect_estimate=estimate,
                ci_low=ci_low,
                ci_high=ci_high,
                i2=i2
            ))

        return NetworkData(
            topic=self.topic,
            treatments=list(self.treatments.values()),
            comparisons=comparisons,
            reference_treatment=self.reference,
            outcome_type=outcome_type,
            effect_measure=effect_measure
        )

    def check_connectivity(self) -> dict:
        """Check if network is connected."""
        if not self.treatments:
            return {"connected": False, "reason": "No treatments"}

        # Build adjacency list
        adj: Dict[str, Set[str]] = {t: set() for t in self.treatments}
        for study in self.studies:
            adj[study["treatment_a"]].add(study["treatment_b"])
            adj[study["treatment_b"]].add(study["treatment_a"])

        # BFS from first treatment
        start = list(self.treatments.keys())[0]
        visited = {start}
        queue = [start]

        while queue:
            node = queue.pop(0)
            for neighbor in adj[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        connected = len(visited) == len(self.treatments)
        disconnected = set(self.treatments.keys()) - visited

        return {
            "connected": connected,
            "n_treatments": len(self.treatments),
            "n_comparisons": len(set(
                tuple(sorted([s["treatment_a"], s["treatment_b"]])) for s in self.studies
            )),
            "n_studies": len(self.studies),
            "disconnected_treatments": list(disconnected) if disconnected else None
        }


def prepare_netmeta_input(network: NetworkData) -> dict:
    """Prepare input for R netmeta package.

    Returns data in format suitable for netmeta::netmeta() or
    netmeta::pairwise() functions.
    """
    # Long format for pairwise data
    pairwise_data = []

    for comp in network.comparisons:
        pairwise_data.append({
            "treat1": comp.treatment_a,
            "treat2": comp.treatment_b,
            "TE": math.log(comp.effect_estimate) if comp.effect_estimate else None,
            "seTE": _estimate_se(comp.ci_low, comp.ci_high) if comp.ci_low and comp.ci_high else None,
            "n1": None,  # Would need from original studies
            "n2": None,
            "event1": None,
            "event2": None,
            "studlab": f"{comp.treatment_a}_vs_{comp.treatment_b}"
        })

    return {
        "format": "netmeta_pairwise",
        "data": pairwise_data,
        "reference": network.reference_treatment,
        "sm": network.effect_measure,
        "r_code_template": _generate_netmeta_code(network)
    }


def _estimate_se(ci_low: float, ci_high: float) -> float:
    """Estimate SE from CI on log scale."""
    if ci_low <= 0 or ci_high <= 0:
        return 0.5
    log_range = math.log(ci_high) - math.log(ci_low)
    return log_range / 3.92


def _generate_netmeta_code(network: NetworkData) -> str:
    """Generate R code for netmeta analysis."""
    return f'''
# R code for network meta-analysis using netmeta
library(netmeta)

# Load data (from JSON export)
data <- read.csv("network_data.csv")

# Run network meta-analysis
nma <- netmeta(
  TE = TE,
  seTE = seTE,
  treat1 = treat1,
  treat2 = treat2,
  studlab = studlab,
  data = data,
  reference.group = "{network.reference_treatment}",
  sm = "{network.effect_measure}",
  common = FALSE,  # Random effects
  details.chkmultiarm = TRUE
)

# Summary
summary(nma)

# Forest plot
forest(nma, reference.group = "{network.reference_treatment}")

# Network graph
netgraph(nma)

# League table
netleague(nma)

# Ranking (P-scores)
netrank(nma)
'''


# ============================================================================
# ESC METHODOLOGY ADDITIONS: SUCRA, League Tables, Inconsistency Testing
# ============================================================================

@dataclass
class TreatmentRanking:
    """Ranking result for a treatment in NMA."""
    treatment_id: str
    treatment_name: str
    sucra: float  # Surface Under Cumulative Ranking (0-1, higher is better)
    p_score: float  # P-score (frequentist analog to SUCRA)
    mean_rank: float
    rank_probabilities: Dict[int, float]  # P(rank=k) for k=1..n_treatments


@dataclass
class LeagueTableCell:
    """Single cell in the league table (pairwise comparison)."""
    treatment_row: str
    treatment_col: str
    effect_estimate: float
    ci_low: float
    ci_high: float
    is_significant: bool
    comparison_type: str  # "direct", "indirect", "mixed"


def calculate_sucra(network: NetworkData) -> Dict[str, TreatmentRanking]:
    """Calculate SUCRA and P-scores for treatment rankings.

    SUCRA (Surface Under Cumulative Ranking) provides a single numeric
    summary of the probability that a treatment is among the best options.

    SUCRA = (sum over k of (n-k)*P(rank=k)) / ((n-1)*n/2)

    Where P(rank=k) is the probability of being ranked k-th best.

    Note: This is a simplified estimation for demonstration.
    Full Bayesian SUCRA requires MCMC sampling (e.g., via gemtc).

    Args:
        network: NetworkData object

    Returns:
        Dict mapping treatment_id to TreatmentRanking
    """
    treatments = [t.id for t in network.treatments]
    n_treatments = len(treatments)

    if n_treatments < 2:
        return {}

    # Get effect estimates vs reference
    effects_vs_ref = _get_effects_vs_reference(network)

    # Estimate ranking probabilities based on effect magnitudes and uncertainty
    rankings = {}

    for treatment_id in treatments:
        effect_data = effects_vs_ref.get(treatment_id)

        if treatment_id == network.reference_treatment:
            # Reference treatment - use null effect
            log_effect = 0.0
            se = 0.1
        elif effect_data:
            log_effect = math.log(effect_data["estimate"]) if effect_data["estimate"] > 0 else 0
            se = effect_data.get("se", 0.1)
        else:
            log_effect = 0.0
            se = 0.3  # Higher uncertainty for missing comparisons

        # Store for ranking calculation
        rankings[treatment_id] = {"log_effect": log_effect, "se": se}

    # Calculate P-scores (frequentist analog to SUCRA)
    # P-score = proportion of treatments worse than this one
    p_scores = {}
    for t1 in treatments:
        p_better_than = 0.0
        for t2 in treatments:
            if t1 == t2:
                continue

            # Probability that t1 is better than t2
            diff = rankings[t1]["log_effect"] - rankings[t2]["log_effect"]
            se_diff = math.sqrt(rankings[t1]["se"]**2 + rankings[t2]["se"]**2)

            if se_diff > 0:
                # For benefit outcomes (HR/RR < 1 is better), lower is better
                z = diff / se_diff
                p_t1_better = _norm_cdf(-z)  # P(t1 < t2 on log scale)
            else:
                p_t1_better = 0.5

            p_better_than += p_t1_better

        # P-score is average probability of being better
        p_scores[t1] = p_better_than / (n_treatments - 1) if n_treatments > 1 else 0.5

    # Estimate rank probabilities using simulation-like approach
    # (Simplified - true SUCRA requires MCMC)
    rank_probs = _estimate_rank_probabilities(rankings, treatments)

    # Calculate SUCRA from rank probabilities
    results = {}
    for treatment_id in treatments:
        probs = rank_probs.get(treatment_id, {})

        # SUCRA formula
        sucra = 0.0
        for k in range(1, n_treatments + 1):
            p_rank_k = probs.get(k, 0.0)
            sucra += (n_treatments - k) * p_rank_k

        if n_treatments > 1:
            sucra = sucra / ((n_treatments - 1) * n_treatments / 2)

        # Mean rank
        mean_rank = sum(k * probs.get(k, 0) for k in range(1, n_treatments + 1))

        treatment_obj = next((t for t in network.treatments if t.id == treatment_id), None)
        treatment_name = treatment_obj.name if treatment_obj else treatment_id

        results[treatment_id] = TreatmentRanking(
            treatment_id=treatment_id,
            treatment_name=treatment_name,
            sucra=round(sucra, 4),
            p_score=round(p_scores.get(treatment_id, 0.5), 4),
            mean_rank=round(mean_rank, 2),
            rank_probabilities={k: round(p, 4) for k, p in probs.items()}
        )

    return results


def _get_effects_vs_reference(network: NetworkData) -> Dict[str, dict]:
    """Get effect estimates for each treatment vs reference."""
    reference = network.reference_treatment
    effects = {}

    for comp in network.comparisons:
        if comp.treatment_a == reference:
            # Reference is treatment_a, so effect is for treatment_b
            effects[comp.treatment_b] = {
                "estimate": 1.0 / comp.effect_estimate if comp.effect_estimate else 1.0,
                "ci_low": 1.0 / comp.ci_high if comp.ci_high else 0.5,
                "ci_high": 1.0 / comp.ci_low if comp.ci_low else 2.0,
                "se": _estimate_se(comp.ci_low, comp.ci_high) if comp.ci_low and comp.ci_high else 0.2
            }
        elif comp.treatment_b == reference:
            # Reference is treatment_b
            effects[comp.treatment_a] = {
                "estimate": comp.effect_estimate,
                "ci_low": comp.ci_low,
                "ci_high": comp.ci_high,
                "se": _estimate_se(comp.ci_low, comp.ci_high) if comp.ci_low and comp.ci_high else 0.2
            }

    return effects


def _estimate_rank_probabilities(rankings: dict, treatments: list) -> Dict[str, Dict[int, float]]:
    """Estimate rank probabilities using parametric bootstrap-like approach.

    Simplified estimation - full implementation would use MCMC.
    """
    n_treatments = len(treatments)
    n_simulations = 1000

    rank_counts = {t: {k: 0 for k in range(1, n_treatments + 1)} for t in treatments}

    import random
    random.seed(42)  # Reproducibility

    for _ in range(n_simulations):
        # Simulate effects
        simulated_effects = {}
        for t in treatments:
            log_effect = rankings[t]["log_effect"]
            se = rankings[t]["se"]
            # Sample from normal distribution
            simulated = log_effect + random.gauss(0, se)
            simulated_effects[t] = simulated

        # Rank treatments (lower effect = better for HR/RR)
        sorted_treatments = sorted(treatments, key=lambda t: simulated_effects[t])

        for rank, t in enumerate(sorted_treatments, 1):
            rank_counts[t][rank] += 1

    # Convert counts to probabilities
    rank_probs = {}
    for t in treatments:
        rank_probs[t] = {k: count / n_simulations for k, count in rank_counts[t].items()}

    return rank_probs


def _norm_cdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def generate_league_table(network: NetworkData) -> Dict[str, any]:
    """Generate league table for all pairwise comparisons.

    The league table shows effect estimates for all treatment pairs.
    Lower triangle: Row vs Column
    Upper triangle: Column vs Row (reciprocal)

    Args:
        network: NetworkData object

    Returns:
        League table data structure
    """
    treatments = [t.id for t in network.treatments]
    n_treatments = len(treatments)

    # Build comparison matrix
    comparisons = {}
    for comp in network.comparisons:
        key_ab = (comp.treatment_a, comp.treatment_b)
        key_ba = (comp.treatment_b, comp.treatment_a)

        comparisons[key_ab] = {
            "estimate": comp.effect_estimate,
            "ci_low": comp.ci_low,
            "ci_high": comp.ci_high,
            "type": "direct"
        }

        # Reciprocal comparison
        if comp.effect_estimate and comp.ci_low and comp.ci_high:
            comparisons[key_ba] = {
                "estimate": 1.0 / comp.effect_estimate,
                "ci_low": 1.0 / comp.ci_high,
                "ci_high": 1.0 / comp.ci_low,
                "type": "direct"
            }

    # Generate league table cells
    cells = []
    matrix = {}

    for i, t_row in enumerate(treatments):
        matrix[t_row] = {}
        for j, t_col in enumerate(treatments):
            if i == j:
                # Diagonal - same treatment
                matrix[t_row][t_col] = None
                continue

            key = (t_row, t_col)
            comp_data = comparisons.get(key)

            if comp_data:
                cell = LeagueTableCell(
                    treatment_row=t_row,
                    treatment_col=t_col,
                    effect_estimate=comp_data["estimate"],
                    ci_low=comp_data["ci_low"],
                    ci_high=comp_data["ci_high"],
                    is_significant=not (comp_data["ci_low"] < 1.0 < comp_data["ci_high"]),
                    comparison_type=comp_data["type"]
                )
            else:
                # Attempt indirect estimation (simplified)
                indirect = _estimate_indirect_comparison(network, t_row, t_col)
                if indirect:
                    cell = LeagueTableCell(
                        treatment_row=t_row,
                        treatment_col=t_col,
                        effect_estimate=indirect["estimate"],
                        ci_low=indirect["ci_low"],
                        ci_high=indirect["ci_high"],
                        is_significant=not (indirect["ci_low"] < 1.0 < indirect["ci_high"]),
                        comparison_type="indirect"
                    )
                else:
                    cell = None

            if cell:
                cells.append({
                    "row": t_row,
                    "col": t_col,
                    "estimate": round(cell.effect_estimate, 4),
                    "ci_low": round(cell.ci_low, 4),
                    "ci_high": round(cell.ci_high, 4),
                    "significant": cell.is_significant,
                    "type": cell.comparison_type
                })
                matrix[t_row][t_col] = cell

    return {
        "treatments": treatments,
        "n_treatments": n_treatments,
        "cells": cells,
        "matrix": _matrix_to_display(matrix, treatments),
        "reference": network.reference_treatment,
        "interpretation": (
            "Values <1 favor row treatment; >1 favor column treatment. "
            "Bolded values are statistically significant (CI excludes 1)."
        )
    }


def _estimate_indirect_comparison(network: NetworkData,
                                   treatment_a: str, treatment_b: str) -> Optional[dict]:
    """Estimate indirect comparison via common comparator (Bucher method).

    For A vs B via C:
    log(θ_AB) = log(θ_AC) - log(θ_BC)
    """
    # Find common comparators
    comparators_a = set()
    comparators_b = set()

    effects = {}
    for comp in network.comparisons:
        key = (comp.treatment_a, comp.treatment_b)
        if comp.effect_estimate and comp.ci_low and comp.ci_high:
            effects[key] = {
                "log_effect": math.log(comp.effect_estimate),
                "se": _estimate_se(comp.ci_low, comp.ci_high)
            }
            # Also store reverse
            effects[(comp.treatment_b, comp.treatment_a)] = {
                "log_effect": -math.log(comp.effect_estimate),
                "se": _estimate_se(comp.ci_low, comp.ci_high)
            }

        if comp.treatment_a == treatment_a:
            comparators_a.add(comp.treatment_b)
        elif comp.treatment_b == treatment_a:
            comparators_a.add(comp.treatment_a)

        if comp.treatment_a == treatment_b:
            comparators_b.add(comp.treatment_b)
        elif comp.treatment_b == treatment_b:
            comparators_b.add(comp.treatment_a)

    common = comparators_a & comparators_b

    if not common:
        return None

    # Use first common comparator
    c = list(common)[0]

    # Get A vs C and B vs C
    ac = effects.get((treatment_a, c)) or effects.get((c, treatment_a))
    bc = effects.get((treatment_b, c)) or effects.get((c, treatment_b))

    if not ac or not bc:
        return None

    # Indirect estimate (Bucher method)
    # If we have A vs C and B vs C, then A vs B = (A vs C) / (B vs C)
    # On log scale: log(A/B) = log(A/C) - log(B/C)

    # Need to handle direction correctly
    log_ac = effects.get((treatment_a, c), {}).get("log_effect")
    log_bc = effects.get((treatment_b, c), {}).get("log_effect")

    if log_ac is None:
        log_ac = -effects.get((c, treatment_a), {}).get("log_effect", 0)
    if log_bc is None:
        log_bc = -effects.get((c, treatment_b), {}).get("log_effect", 0)

    log_ab = log_ac - log_bc

    se_ac = ac.get("se", 0.2)
    se_bc = bc.get("se", 0.2)
    se_ab = math.sqrt(se_ac**2 + se_bc**2)

    return {
        "estimate": math.exp(log_ab),
        "ci_low": math.exp(log_ab - 1.96 * se_ab),
        "ci_high": math.exp(log_ab + 1.96 * se_ab),
        "se": se_ab,
        "via": c
    }


def _matrix_to_display(matrix: dict, treatments: list) -> List[List[str]]:
    """Convert matrix to display format."""
    header = [""] + treatments
    rows = [header]

    for t_row in treatments:
        row = [t_row]
        for t_col in treatments:
            if t_row == t_col:
                row.append("-")
            else:
                cell = matrix.get(t_row, {}).get(t_col)
                if cell:
                    sig_marker = "*" if cell.is_significant else ""
                    row.append(f"{cell.effect_estimate:.2f}{sig_marker}")
                else:
                    row.append("N/A")
        rows.append(row)

    return rows


def loop_inconsistency_test(network: NetworkData) -> Dict[str, any]:
    """Test for loop inconsistency in the network.
    
    A loop is formed when there is direct and indirect evidence for a comparison.
    The simplest loop is a triangle (A-B, B-C, C-A).
    
    Inconsistency (L) = |log(θ_AB_direct) - log(θ_AB_indirect)|
    """
    loops = []
    
    # 1. Identify all triangular loops
    treatments = [t.id for t in network.treatments]
    comparisons = {}
    for comp in network.comparisons:
        if comp.effect_estimate and comp.ci_low and comp.ci_high:
            comparisons[tuple(sorted([comp.treatment_a, comp.treatment_b]))] = comp

    for i in range(len(treatments)):
        for j in range(i + 1, len(treatments)):
            for k in range(j + 1, len(treatments)):
                t1, t2, t3 = treatments[i], treatments[j], treatments[k]
                
                # Check if all three sides of the triangle exist
                c12 = comparisons.get(tuple(sorted([t1, t2])))
                c23 = comparisons.get(tuple(sorted([t2, t3])))
                c31 = comparisons.get(tuple(sorted([t3, t1])))
                
                if c12 and c23 and c31:
                    # Found a loop!
                    # θ_13_indirect = θ_12_direct * θ_23_direct
                    # If we use log scale: log(θ_13_indirect) = log(θ_12) + log(θ_23)
                    
                    # Need to be careful with direction
                    log_12 = math.log(c12.effect_estimate) if c12.treatment_a == t1 else -math.log(c12.effect_estimate)
                    log_23 = math.log(c23.effect_estimate) if c23.treatment_a == t2 else -math.log(c23.effect_estimate)
                    log_31 = math.log(c31.effect_estimate) if c31.treatment_a == t3 else -math.log(c31.effect_estimate)
                    
                    # Inconsistency factor (IF)
                    # For a closed loop: log(θ_12) + log(θ_23) + log(θ_31) should be 0
                    if_val = log_12 + log_23 + log_31
                    
                    se_12 = _estimate_se(c12.ci_low, c12.ci_high)
                    se_23 = _estimate_se(c23.ci_low, c23.ci_high)
                    se_31 = _estimate_se(c31.ci_low, c31.ci_high)
                    
                    se_if = math.sqrt(se_12**2 + se_23**2 + se_31**2)
                    
                    z = if_val / se_if if se_if > 0 else 0
                    p_value = 2 * (1 - _norm_cdf(abs(z)))
                    
                    loops.append({
                        "loop": f"{t1}-{t2}-{t3}",
                        "if_value": round(if_val, 4),
                        "se_if": round(se_if, 4),
                        "p_value": round(p_value, 6),
                        "inconsistent": p_value < 0.05
                    })

    return {
        "test_type": "loop_inconsistency",
        "n_loops_found": len(loops),
        "results": loops,
        "any_inconsistency": any(l["inconsistent"] for l in loops)
    }


def node_splitting_test(network: NetworkData) -> Dict[str, any]:
    """Test for inconsistency using node-splitting approach.

    Node-splitting separates direct and indirect evidence for each comparison
    and tests whether they agree.

    Note: This is a simplified implementation. Full node-splitting requires
    proper network models (gemtc or netmeta).

    Args:
        network: NetworkData object

    Returns:
        Inconsistency test results
    """
    results = []

    for comp in network.comparisons:
        if comp.n_studies == 0:
            continue

        t_a, t_b = comp.treatment_a, comp.treatment_b

        # Direct evidence
        direct_log = math.log(comp.effect_estimate) if comp.effect_estimate else 0
        direct_se = _estimate_se(comp.ci_low, comp.ci_high) if comp.ci_low and comp.ci_high else 0.3

        # Indirect evidence (via other paths)
        indirect = _estimate_indirect_comparison(network, t_a, t_b)

        if indirect and indirect.get("estimate"):
            indirect_log = math.log(indirect["estimate"])
            indirect_se = indirect.get("se", 0.3)

            # Test for inconsistency
            diff = direct_log - indirect_log
            se_diff = math.sqrt(direct_se**2 + indirect_se**2)

            if se_diff > 0:
                z = diff / se_diff
                p_value = 2 * (1 - _norm_cdf(abs(z)))
            else:
                p_value = 1.0

            results.append({
                "comparison": f"{t_a} vs {t_b}",
                "direct": {
                    "estimate": round(comp.effect_estimate, 4),
                    "se": round(direct_se, 4)
                },
                "indirect": {
                    "estimate": round(indirect["estimate"], 4),
                    "se": round(indirect_se, 4),
                    "via": indirect.get("via")
                },
                "difference": round(math.exp(diff), 4),
                "z_statistic": round(z, 4) if se_diff > 0 else None,
                "p_value": round(p_value, 6),
                "inconsistent": p_value < 0.10
            })

    any_inconsistent = any(r["inconsistent"] for r in results)

    return {
        "test_type": "node_splitting",
        "n_comparisons_tested": len(results),
        "results": results,
        "any_inconsistency": any_inconsistent,
        "global_interpretation": (
            "CAUTION: Significant inconsistency detected between direct and indirect evidence. "
            "Network estimates may be unreliable."
            if any_inconsistent else
            "No significant inconsistency detected between direct and indirect evidence."
        ),
        "note": "Simplified node-splitting. For rigorous testing, use R netmeta::netsplit() or gemtc."
    }


def generate_enhanced_r_code(network: NetworkData) -> str:
    """Generate comprehensive R code for NMA with SUCRA and league tables.

    Args:
        network: NetworkData object

    Returns:
        R code string for full NMA analysis
    """
    treatments_str = ", ".join(f'"{t.id}"' for t in network.treatments)

    return f'''
# =============================================================================
# Network Meta-Analysis: {network.topic}
# Generated by LEC Pipeline
# =============================================================================

library(netmeta)
library(dplyr)

# --- Data Preparation ---
# Load from exported JSON/CSV
data <- read.csv("network_data.csv")

# --- Network Meta-Analysis (Random Effects) ---
nma <- netmeta(
  TE = TE,
  seTE = seTE,
  treat1 = treat1,
  treat2 = treat2,
  studlab = studlab,
  data = data,
  reference.group = "{network.reference_treatment}",
  sm = "{network.effect_measure}",
  common = FALSE,
  random = TRUE,
  details.chkmultiarm = TRUE
)

# --- Summary Statistics ---
cat("\\n=== Network Meta-Analysis Summary ===\\n")
print(summary(nma))

# --- Forest Plot ---
pdf("forest_plot.pdf", width = 10, height = 8)
forest(nma,
       reference.group = "{network.reference_treatment}",
       sortvar = TE,
       smlab = "{network.effect_measure}")
dev.off()

# --- Network Graph ---
pdf("network_graph.pdf", width = 8, height = 8)
netgraph(nma,
         plastic = TRUE,
         thickness = "n.studies",
         number.of.studies = TRUE)
dev.off()

# --- League Table ---
cat("\\n=== League Table ===\\n")
league <- netleague(nma, bracket = "(", separator = " to ")
print(league)

# Export league table
write.csv(league$random, "league_table.csv")

# --- Treatment Rankings (P-scores) ---
cat("\\n=== Treatment Rankings ===\\n")
rank_results <- netrank(nma, small.values = "good")
print(rank_results)

# SUCRA-equivalent (P-scores)
cat("\\n=== P-scores (Frequentist SUCRA) ===\\n")
print(data.frame(
  Treatment = rownames(rank_results$ranking.random),
  P_score = round(rank_results$ranking.random, 4)
))

# --- Rankogram ---
pdf("rankogram.pdf", width = 10, height = 6)
rankogram(rank_results)
dev.off()

# --- Inconsistency Testing ---
cat("\\n=== Inconsistency Testing ===\\n")

# Global inconsistency (design-by-treatment interaction)
decomp <- decomp.design(nma)
print(decomp)

# Node-splitting (local inconsistency)
if (nma$d > 1) {{
  split <- netsplit(nma)
  cat("\\n=== Node-Splitting Results ===\\n")
  print(split)

  # Forest plot of direct vs indirect
  pdf("nodesplit_forest.pdf", width = 10, height = 8)
  forest(split, show = "all")
  dev.off()
}}

# --- Funnel Plot (comparison-adjusted) ---
pdf("funnel_plot.pdf", width = 8, height = 6)
funnel(nma, order = c({treatments_str}))
dev.off()

# --- Export Results ---
results <- list(
  summary = summary(nma),
  league_table = league$random,
  p_scores = rank_results$ranking.random,
  reference = "{network.reference_treatment}"
)

saveRDS(results, "nma_results.rds")

cat("\\n=== Analysis Complete ===\\n")
cat("Output files: forest_plot.pdf, network_graph.pdf, league_table.csv,\\n")
cat("              rankogram.pdf, nodesplit_forest.pdf, funnel_plot.pdf\\n")
'''
