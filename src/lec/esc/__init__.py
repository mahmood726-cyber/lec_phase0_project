"""ESC (European Society of Cardiology) Guideline Support Module.

Provides tools for ESC guideline development:
- Recommendation class derivation (I, IIa, IIb, III)
- Level of evidence assignment (A, B, C)
- Standardized recommendation wording
"""

from lec.esc.recommendation import (
    ESCRecommendation,
    RecommendationClass,
    EvidenceLevel,
    derive_recommendation
)

__all__ = [
    "ESCRecommendation",
    "RecommendationClass",
    "EvidenceLevel",
    "derive_recommendation"
]
