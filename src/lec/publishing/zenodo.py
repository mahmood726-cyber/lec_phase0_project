"""Zenodo Packer - Creates release-ready artifact bundles."""

import shutil
import zipfile
import tempfile
from pathlib import Path
from typing import Optional

from lec.core import load_json, write_json, utc_now_iso


class ZenodoPacker:
    """Packages LEC artifacts for Zenodo deposition."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def pack(self, lec_path: Path, methods_path: Optional[Path] = None, 
             topic: Optional[str] = None) -> Path:
        """Create Zenodo-ready ZIP bundle from LEC object.

        Args:
            lec_path: Path to the main LEC JSON object
            methods_path: Optional path to custom METHODS.md
            topic: Optional topic override for naming

        Returns:
            Path to the created ZIP file
        """
        # Load LEC object to find artifacts
        lec_data = load_json(lec_path)
        if not topic:
            topic = lec_data.get("question", {}).get("title", "lec_bundle").replace(" ", "_").lower()
        
        run_id = lec_data.get("reproducibility", {}).get("run_id", "unknown")

        # Prepare staging directory using tempfile
        bundle_name = f"lec_bundle_{topic}_{run_id}"
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = Path(tmp_dir) / bundle_name
            bundle_dir.mkdir(parents=True)

            # 1. Copy main LEC object
            shutil.copy2(lec_path, bundle_dir / "lec_object.json")

            # 2. Copy artifacts referenced in LEC object
            self._copy_artifacts(lec_data, bundle_dir)

            # 3. Add METHODS.md
            if methods_path and methods_path.exists():
                shutil.copy2(methods_path, bundle_dir / "METHODS.md")
            else:
                # Create default README/METHODS if missing
                self._create_default_methods(bundle_dir, topic, run_id)

            # 4. Create Zenodo metadata
            self._create_metadata(bundle_dir, lec_data)

            # 5. Zip it up
            zip_path = self.output_dir / f"{bundle_name}.zip"
            self._create_zip(bundle_dir, zip_path)

        return zip_path

    def _copy_artifacts(self, lec_data: dict, dest_dir: Path):
        """Copy referenced artifacts to bundle."""
        # Helper to copy if path exists
        def safe_copy(src_str, dest_name):
            if not src_str:
                return
            src = Path(src_str)
            if src.exists():
                shutil.copy2(src, dest_dir / dest_name)
            else:
                print(f"Warning: Artifact not found: {src}")

        # Discovery
        universe = lec_data.get("evidence_universe", {})
        for idx, artifact in enumerate(universe.get("discovery_artifacts", [])):
            safe_copy(artifact.get("path"), f"discovery_{idx}.json")

        # Verification
        verification = lec_data.get("verification", {}).get("truthcert", {})
        safe_copy(verification.get("certificate", {}).get("path"), "truthcert.json")
        safe_copy(verification.get("audit_log", {}).get("path"), "audit_log.json")

        # Analysis
        analysis = lec_data.get("analysis", {})
        contract = analysis.get("metaengine_contract", {})
        safe_copy(contract.get("input", {}).get("path"), "metaengine_input.json")
        safe_copy(contract.get("output", {}).get("path"), "metaengine_output.json")

        # Reproducibility (Manifest)
        manifest = lec_data.get("reproducibility", {}).get("manifest", {})
        safe_copy(manifest.get("path"), "manifest.json")

    def _create_default_methods(self, bundle_dir: Path, topic: str, run_id: str):
        """Create default README/METHODS file."""
        content = f"""# LEC Bundle: {topic}
Run ID: {run_id}
Generated: {utc_now_iso()}

## Contents
- lec_object.json: Main Living Evidence Composite object
- truthcert.json: Verification certificate (Bronze)
- audit_log.json: Detailed verification audit trail
- metaengine_input/output.json: Analysis inputs and results
- discovery_*.json: Search results and candidate lists
- manifest.json: File integrity manifest

## Usage
This bundle contains all artifacts required to reproduce the meta-analysis for this topic.
"""
        with open(bundle_dir / "README.md", "w", encoding="utf-8") as f:
            f.write(content)

    def _create_metadata(self, bundle_dir: Path, lec_data: dict):
        """Create Zenodo metadata JSON."""
        question = lec_data.get("question", {})
        metadata = {
            "metadata": {
                "title": f"Living Evidence Composite: {question.get('title', 'Untitled')}",
                "upload_type": "dataset",
                "description": f"Automated meta-analysis bundle for: {question.get('pico', {}).get('population')} - {question.get('pico', {}).get('intervention')}",
                "creators": [{"name": "LEC Phase 0 Pipeline"}],
                "keywords": question.get("keywords", []) + ["meta-analysis", "living evidence"],
                "license": "cc-by-4.0"
            }
        }
        write_json(bundle_dir / ".zenodo.json", metadata)

    def _create_zip(self, source_dir: Path, output_path: Path):
        """Create ZIP archive."""
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in source_dir.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(source_dir))
