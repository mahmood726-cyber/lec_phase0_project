"""Cochrane501 Trial Discovery Index - Precision Layer.

Uses Cochrane501 inclusion decisions to rank/filter trial candidates
produced by AACT (recall layer).
"""

from pathlib import Path
from typing import Optional

import yaml

from lec.core import write_json, load_json, utc_now_iso


class Cochrane501Ranker:
    """Ranks trial candidates using Cochrane501 indices."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize ranker with config.

        Args:
            config_path: Path to discovery.yaml config
        """
        self.config = self._load_config(config_path)
        self.weights = self.config.get("weights", {
            "ma_match": 0.45,
            "cooccur": 0.35,
            "term": 0.20
        })
        self.thresholds = self.config.get("thresholds", {
            "include": 0.75,
            "flag": 0.55
        })

    def _load_config(self, config_path: Optional[Path]) -> dict:
        """Load config from YAML file."""
        if config_path and config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}

    def rank(self, topic: str, candidates_path: Path,
             output_dir: Path) -> Path:
        """Rank candidates using Cochrane501 indices.

        Args:
            topic: Topic identifier
            candidates_path: Path to AACT candidates JSON/parquet
            output_dir: Output directory

        Returns:
            Path to ranked discovery output
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load candidates
        candidates = self._load_candidates(candidates_path)

        # Score and rank each candidate
        ranked = []
        for candidate in candidates:
            scored = self._score_candidate(candidate)
            ranked.append(scored)

        # Sort by total score descending
        ranked.sort(key=lambda x: x.get("cochrane_score", 0), reverse=True)

        # Add ranks
        for i, candidate in enumerate(ranked):
            candidate["rank"] = i + 1

        # Triage based on combined score
        for candidate in ranked:
            combined = (
                candidate.get("score_total", 0) * 0.5 +
                candidate.get("cochrane_score", 0) * 0.5
            )
            candidate["combined_score"] = round(combined, 4)

            if combined >= self.thresholds["include"]:
                candidate["final_disposition"] = "INCLUDE"
            elif combined >= self.thresholds["flag"]:
                candidate["final_disposition"] = "FLAG"
            else:
                candidate["final_disposition"] = "EXCLUDE"

        # Build output
        result = {
            "topic": topic,
            "created_at_utc": utc_now_iso(),
            "source": "cochrane501_ranked",
            "candidates_source": str(candidates_path),
            "config": self.config,
            "statistics": {
                "total_candidates": len(ranked),
                "included": sum(1 for c in ranked if c["final_disposition"] == "INCLUDE"),
                "flagged": sum(1 for c in ranked if c["final_disposition"] == "FLAG"),
                "excluded": sum(1 for c in ranked if c["final_disposition"] == "EXCLUDE")
            },
            "prisma": {
                "identified": len(ranked),
                "screened": len(ranked),
                "excluded": sum(1 for c in ranked if c["final_disposition"] == "EXCLUDE"),
                "included": sum(1 for c in ranked if c["final_disposition"] == "INCLUDE")
            },
            "discovered_trials": ranked
        }

        output_path = output_dir / f"discovery_{topic}_{utc_now_iso()[:10]}.json"
        write_json(output_path, result)
        return output_path

    def _load_candidates(self, candidates_path: Path) -> list[dict]:
        """Load candidates from JSON or parquet."""
        if candidates_path.suffix == ".json":
            data = load_json(candidates_path)
            return data.get("candidates", data.get("discovered_trials", []))
        elif candidates_path.suffix == ".parquet":
            try:
                import pandas as pd
                df = pd.read_parquet(candidates_path)
                return df.to_dict(orient="records")
            except ImportError:
                raise RuntimeError("pandas/pyarrow required for parquet files")
        else:
            raise ValueError(f"Unsupported file format: {candidates_path.suffix}")

    def _score_candidate(self, candidate: dict) -> dict:
        """Score a candidate using Cochrane501 signals.

        In a full implementation, this would:
        1. Look up trial in cochrane501_trial.parquet
        2. Find matching MAs in cochrane501_ma_trial.parquet
        3. Compute term similarity from cochrane501_term_index.parquet
        4. Find co-occurrence neighbors from cochrane501_cooccurrence.parquet

        For Phase 0 demo, we use simplified scoring.
        """
        result = candidate.copy()

        # Demo scoring based on available fields
        ma_score = 0.0
        cooccur_score = 0.0
        term_score = 0.0

        # Higher score for completed trials with results
        if candidate.get("overall_status") == "Completed":
            ma_score += 0.3
        if candidate.get("has_results") or candidate.get("results_first_posted_date"):
            ma_score += 0.2

        # Phase bonus
        phase = candidate.get("phase", "")
        if "Phase 3" in str(phase) or "Phase 4" in str(phase):
            term_score += 0.3
        elif "Phase 2" in str(phase):
            term_score += 0.2

        # Randomization bonus
        allocation = candidate.get("allocation") or ""
        if allocation.lower().startswith("random"):
            cooccur_score += 0.3

        # Calculate weighted score
        cochrane_score = (
            self.weights["ma_match"] * ma_score +
            self.weights["cooccur"] * cooccur_score +
            self.weights["term"] * term_score
        )

        result["cochrane_score"] = round(cochrane_score, 4)
        result["score_components"] = {
            "ma_match": round(ma_score, 4),
            "cooccur": round(cooccur_score, 4),
            "term": round(term_score, 4)
        }
        result["provenance"] = {
            "matched_mas": [],  # Would be populated from index
            "term_matches": [],
            "co_occurrence_sources": [],
            "discovery_method": "aact_mesh_sql"
        }

        return result
