"""Linker - Deterministic ID matching and resolution."""

import difflib
from pathlib import Path
from typing import List, Dict, Optional, Union

from lec.core import write_json, utc_now_iso


class Linker:
    """Links trial candidates from different sources."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def link(self, source_a: Union[List[Dict], Dict], source_b: Union[List[Dict], Dict], 
             topic: str) -> Path:
        """Link candidates from two sources.
        
        Args:
            source_a: First source (list of candidates or dict wrapper)
            source_b: Second source (list of candidates or dict wrapper)
            topic: Topic identifier
        """
        # Normalize inputs
        candidates_a = self._normalize_input(source_a)
        candidates_b = self._normalize_input(source_b)
        
        links = []
        unlinked_a = []
        unlinked_b = list(candidates_b)  # Copy to track unmatched
        
        for item_a in candidates_a:
            match = self._find_match(item_a, unlinked_b)
            if match:
                links.append({
                    "source_a_id": self._get_id(item_a),
                    "source_b_id": self._get_id(match["item"]),
                    "confidence": match["confidence"],
                    "method": match["method"],
                    "merged": self._merge(item_a, match["item"])
                })
                # Remove from unlinked_b
                if match["item"] in unlinked_b:
                    unlinked_b.remove(match["item"])
            else:
                unlinked_a.append(item_a)

        result = {
            "topic": topic,
            "created_at_utc": utc_now_iso(),
            "linked_count": len(links),
            "unlinked_a_count": len(unlinked_a),
            "unlinked_b_count": len(unlinked_b),
            "links": links,
            "unlinked_a": unlinked_a,
            "unlinked_b": unlinked_b
        }
        
        output_path = self.output_dir / f"linking_{topic}.json"
        write_json(output_path, result)
        
        return output_path

    def _normalize_input(self, source: Union[List[Dict], Dict]) -> List[Dict]:
        """Normalize input to list of dicts."""
        if source is None:
            return []
        if isinstance(source, list):
            return source
        if isinstance(source, dict):
            # Try common keys
            for key in ["candidates", "discovered_trials", "articles"]:
                if key in source and isinstance(source[key], list):
                    return source[key]
            # If no common keys, maybe it is a single item (not likely but safe)
            if source:
                return [source]
        return []

    def _find_match(self, item_a: Dict, candidates_b: List[Dict]) -> Optional[Dict]:
        """Find best match for item_a in candidates_b."""
        # 1. Exact ID match (NCT, DOI, PMID)
        for item_b in candidates_b:
            if self._ids_match(item_a, item_b):
                return {
                    "item": item_b,
                    "confidence": 1.0,
                    "method": "exact_id"
                }
        
        # 2. Title similarity (if high confidence)
        title_a = self._normalize_title(item_a.get("title") or item_a.get("brief_title"))
        if not title_a:
            return None
            
        best_match = None
        best_ratio = 0.0
        
        for item_b in candidates_b:
            title_b = self._normalize_title(item_b.get("title") or item_b.get("brief_title"))
            if not title_b:
                continue
                
            ratio = difflib.SequenceMatcher(None, title_a, title_b).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = item_b
        
        if best_match and best_ratio > 0.85: # Slightly lower threshold with normalization
            return {
                "item": best_match,
                "confidence": best_ratio,
                "method": "title_similarity"
            }
            
        return None

    def _normalize_title(self, title: Optional[str]) -> str:
        """Normalize title for comparison."""
        if not title:
            return ""
        # Lowercase and remove punctuation
        import re
        t = title.lower()
        t = re.sub(r'[^\w\s]', '', t)
        return " ".join(t.split())

    def _ids_match(self, item_a: Dict, item_b: Dict) -> bool:
        """Check if any IDs match exactly."""
        # NCT
        nct_a = item_a.get("nct_id")
        nct_b = item_b.get("nct_id")
        if nct_a and nct_b and nct_a == nct_b:
            return True
            
        # DOI
        doi_a = item_a.get("doi")
        doi_b = item_b.get("doi")
        if doi_a and doi_b and doi_a.lower() == doi_b.lower():
            return True
            
        # PMID
        pmid_a = item_a.get("pmid")
        pmid_b = item_b.get("pmid")
        if pmid_a and pmid_b and str(pmid_a) == str(pmid_b):
            return True
            
        return False

    def _get_id(self, item: Dict) -> str:
        """Get best display ID for item."""
        return (item.get("nct_id") or 
                item.get("doi") or 
                item.get("pmid") or 
                item.get("title", "unknown")[:20])

    def _merge(self, item_a: Dict, item_b: Dict) -> Dict:
        """Merge two items, preferring A but filling from B."""
        merged = item_a.copy()
        for k, v in item_b.items():
            if k not in merged or not merged[k]:
                merged[k] = v
        return merged
