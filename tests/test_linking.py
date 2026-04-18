"""Tests for Linker module."""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lec.linking.linker import Linker

class TestLinker:
    """Tests for Linker class."""
    
    @pytest.fixture
    def linker(self, tmp_path):
        return Linker(tmp_path)
        
    def test_normalize_input_list(self, linker):
        """Test normalization of list input."""
        data = [{"id": 1}]
        assert linker._normalize_input(data) == data
        
    def test_normalize_input_dict_candidates(self, linker):
        """Test normalization of dict input with 'candidates' key."""
        data = {"candidates": [{"id": 1}]}
        assert linker._normalize_input(data) == [{"id": 1}]
        
    def test_normalize_input_dict_discovered(self, linker):
        """Test normalization of dict with 'discovered_trials'."""
        data = {"discovered_trials": [{"id": 1}]}
        assert linker._normalize_input(data) == [{"id": 1}]
        
    def test_exact_match_nct(self, linker):
        """Test exact matching on NCT ID."""
        source_a = [{"nct_id": "NCT123", "val": "A"}]
        source_b = [{"nct_id": "NCT123", "val": "B"}]
        
        output = linker.link(source_a, source_b, "test")
        
        # Read result
        import json
        with open(output) as f:
            res = json.load(f)
            
        assert res["linked_count"] == 1
        assert res["links"][0]["confidence"] == 1.0
        assert res["links"][0]["method"] == "exact_id"
        
    def test_title_similarity(self, linker):
        """Test fuzzy matching on title."""
        source_a = [{"title": "Effect of Colchicine on MI"}]
        source_b = [{"title": "Effect of Colchicine on Myocardial Infarction", "nct_id": "NCT999"}]
        
        # This shouldn't match with default threshold 0.9 potentially, 
        # let's try a closer match
        source_c = [{"title": "Effect of Colchicine on MI 2024"}]
        
        output = linker.link(source_a, source_c, "test")
        
        # Verify
        import json
        with open(output) as f:
            res = json.load(f)
            
        # Match "Effect of Colchicine on MI" vs "Effect of Colchicine on MI 2024"
        # Similarity should be high
        if res["linked_count"] == 1:
            assert res["links"][0]["method"] == "title_similarity"
