"""Multi-agent extraction system.

Implements dual-agent extraction as per Phase 0:
- Agent A: deterministic rules-based extractor
- Agent B: independent extractor (LLM or alternate rules profile)
- Comparator: generates field-level disagreement artifacts
"""

from lec.extraction.rules_agent import RulesExtractor
from lec.extraction.comparator import ExtractionComparator
from lec.extraction.runner import run_extraction

__all__ = [
    "RulesExtractor",
    "ExtractionComparator",
    "run_extraction",
]
