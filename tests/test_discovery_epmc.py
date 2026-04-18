"""Tests for Europe PMC Discovery module."""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lec.discovery.europe_pmc import EuropePMCIndex

class TestEuropePMCIndex:
    """Tests for EuropePMCIndex."""

    @pytest.fixture
    def epmc(self, tmp_path):
        return EuropePMCIndex(tmp_path, demo_mode=True)

    def test_search_demo(self, epmc):
        """Test search in demo mode."""
        articles = epmc.search("test query")
        assert len(articles) == 2
        assert articles[0]["pmcid"] == "PMC123456"

    def test_download_pdf_demo(self, epmc):
        """Test PDF download in demo mode."""
        path = epmc.download_pdf("PMC123456")
        assert path is not None
        assert path.exists()
        assert path.name == "PMC123456.pdf"
        
        with open(path, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-"

    def test_run_demo(self, epmc):
        """Test full run in demo mode."""
        output_path = epmc.run("topic_id", "query")
        assert output_path.exists()
        
        import json
        with open(output_path) as f:
            res = json.load(f)
            
        assert res["topic"] == "topic_id"
        assert res["downloaded"] == 2
        assert len(res["articles"]) == 2
