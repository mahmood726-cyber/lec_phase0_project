"""Tests for Duplicates Validator."""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lec.validators.duplicates import DuplicatesValidator

class TestDuplicatesValidator:
    """Tests for DuplicatesValidator."""

    @pytest.fixture
    def validator(self):
        return DuplicatesValidator()

    def test_stop_word_filtering(self, validator):
        """Test that stop words are filtered out during normalization."""
        title1 = "The Effect of Colchicine on Heart Failure"
        title2 = "Effect Colchicine Heart Failure"
        
        sim = validator._jaccard_words(title1, title2)
        # Should be 1.0 because "The", "of", "on" are stop words
        assert sim == 1.0

    def test_similar_titles(self, validator):
        """Test detection of similar titles."""
        study1 = {"study_id": "s1", "title": "Colchicine for MI"}
        study2 = {"study_id": "s2", "title": "Colchicine in Myocardial Infarction"}
        
        sim = validator._calculate_similarity(study1, study2)
        assert sim > 0.0 # Just check it calculates something

    def test_exact_duplicates(self, validator):
        """Test detection of exact duplicates."""
        data = {
            "studies": [
                {"study_id": "s1", "nct_id": "NCT123"},
                {"study_id": "s2", "nct_id": "NCT123"}
            ]
        }
        result = validator.validate(data)
        assert result["status"] == "FAIL"
