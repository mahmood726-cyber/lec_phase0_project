"""Tests for Zenodo Publishing module."""

import pytest
import sys
import shutil
import zipfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lec.publishing.zenodo import ZenodoPacker
from lec.core import write_json

class TestZenodoPacker:
    """Tests for ZenodoPacker."""

    @pytest.fixture
    def packer(self, tmp_path):
        return ZenodoPacker(tmp_path / "output")

    def test_pack_basic(self, packer, tmp_path):
        """Test packing a basic LEC object."""
        # Create dummy artifacts
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        
        discovery_path = artifacts_dir / "discovery.json"
        write_json(discovery_path, {"test": "discovery"})
        
        cert_path = artifacts_dir / "cert.json"
        write_json(cert_path, {"test": "cert"})
        
        # Create LEC object
        lec_data = {
            "question": {"title": "Test Topic"},
            "reproducibility": {
                "run_id": "run_123",
                "manifest": {"path": str(artifacts_dir / "manifest.json")} # Missing file, should warn
            },
            "evidence_universe": {
                "discovery_artifacts": [{"path": str(discovery_path)}]
            },
            "verification": {
                "truthcert": {
                    "certificate": {"path": str(cert_path)}
                }
            }
        }
        lec_path = artifacts_dir / "lec_object.json"
        write_json(lec_path, lec_data)
        
        # Run pack
        zip_path = packer.pack(lec_path)
        
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        
        # Verify contents
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert "lec_object.json" in names
            assert "discovery_0.json" in names
            assert "truthcert.json" in names
            assert "README.md" in names
            assert ".zenodo.json" in names
            # Manifest was missing, so not in zip
            assert "manifest.json" not in names

