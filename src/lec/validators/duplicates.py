"""Duplicates Validator.

Detects potential duplicate studies based on:
- Identical trial_keys (NCT IDs, PMIDs, DOIs)
- Similar study characteristics (N, intervention, comparator)
- Title similarity
"""

import re
from collections import defaultdict

from lec.validators.base import BaseValidator


class DuplicatesValidator(BaseValidator):
    """Detects duplicate studies in extraction."""

    name = "duplicates"
    description = "Detects potential duplicate studies"

    # Minimum Jaccard similarity for title match
    TITLE_SIMILARITY_THRESHOLD = 0.7

    # Common stop words in medical titles
    STOP_WORDS = {
        "the", "a", "an", "in", "on", "of", "for", "with", "to", "and", "or",
        "study", "trial", "randomized", "controlled", "clinical", "comparison",
        "efficacy", "safety", "effect", "effects", "patients", "treatment",
        "vs", "versus", "group", "analysis", "evaluation", "assessment"
    }

    def validate(self, extraction_data: dict) -> dict:
        """Check for duplicates across all studies."""
        issues = []
        studies = extraction_data.get("studies", [])

        if len(studies) < 2:
            return self._make_result("PASS", [])

        # Check for exact ID duplicates
        id_issues = self._check_id_duplicates(studies)
        issues.extend(id_issues)

        # Check for similar studies
        similarity_issues = self._check_similarity_duplicates(studies)
        issues.extend(similarity_issues)

        # Determine overall status
        if any(i["severity"] == "error" for i in issues):
            status = "FAIL"
        elif issues:
            status = "FLAG"
        else:
            status = "PASS"

        return self._make_result(status, issues)

    def _check_id_duplicates(self, studies: list[dict]) -> list[dict]:
        """Check for duplicate NCT IDs, PMIDs, or DOIs."""
        issues = []

        id_fields = ["nct_id", "pmid", "doi", "trial_key"]
        for field in id_fields:
            seen = defaultdict(list)
            for study in studies:
                value = study.get(field)
                if value:
                    seen[value].append(study.get("study_id", "unknown"))

            for id_value, study_ids in seen.items():
                if len(study_ids) > 1:
                    issues.append(self._make_issue(
                        study_ids[0],
                        field,
                        f"Duplicate {field}: '{id_value}' appears in {len(study_ids)} studies",
                        severity="error",
                        details={
                            "duplicate_id": id_value,
                            "affected_studies": study_ids
                        }
                    ))

        return issues

    def _check_similarity_duplicates(self, studies: list[dict]) -> list[dict]:
        """Check for similar studies that might be duplicates."""
        issues = []

        for i, study1 in enumerate(studies):
            for study2 in studies[i + 1:]:
                similarity = self._calculate_similarity(study1, study2)

                if similarity >= 0.9:
                    severity = "error"
                    msg = "Highly likely duplicate"
                elif similarity >= 0.7:
                    severity = "warning"
                    msg = "Potential duplicate"
                else:
                    continue

                issues.append(self._make_issue(
                    study1.get("study_id", "unknown"),
                    "duplicate_check",
                    f"{msg}: studies '{study1.get('study_id')}' and "
                    f"'{study2.get('study_id')}' have {similarity:.0%} similarity",
                    severity=severity,
                    details={
                        "study_1": study1.get("study_id"),
                        "study_2": study2.get("study_id"),
                        "similarity_score": similarity
                    }
                ))

        return issues

    def _calculate_similarity(self, study1: dict, study2: dict) -> float:
        """Calculate similarity score between two studies."""
        scores = []
        weights = []

        # Title similarity (Jaccard on words)
        title1 = study1.get("title", "")
        title2 = study2.get("title", "")
        if title1 and title2:
            title_sim = self._jaccard_words(title1, title2)
            scores.append(title_sim)
            weights.append(0.4)

        # N total similarity
        n1 = study1.get("n_total")
        n2 = study2.get("n_total")
        if n1 and n2:
            n_sim = 1.0 if n1 == n2 else max(0, 1 - abs(n1 - n2) / max(n1, n2))
            scores.append(n_sim)
            weights.append(0.2)

        # Author similarity
        authors1 = study1.get("authors", [])
        authors2 = study2.get("authors", [])
        if authors1 and authors2:
            # Check first author
            if isinstance(authors1, list) and isinstance(authors2, list):
                first1 = authors1[0] if authors1 else ""
                first2 = authors2[0] if authors2 else ""
                author_sim = 1.0 if first1.lower() == first2.lower() else 0.0
                scores.append(author_sim)
                weights.append(0.2)

        # Year similarity
        year1 = study1.get("year")
        year2 = study2.get("year")
        if year1 and year2:
            year_sim = 1.0 if year1 == year2 else 0.0
            scores.append(year_sim)
            weights.append(0.2)

        if not scores:
            return 0.0

        # Weighted average
        total_weight = sum(weights)
        return sum(s * w for s, w in zip(scores, weights)) / total_weight

    def _jaccard_words(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity on word sets."""
        words1 = set(self._normalize_text(text1).split())
        words2 = set(self._normalize_text(text2).split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison (remove stop words)."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        words = text.split()
        filtered_words = [w for w in words if w not in self.STOP_WORDS]
        return " ".join(filtered_words)
