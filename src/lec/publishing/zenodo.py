"""Zenodo Packer - Creates release-ready artifact bundles."""

import hashlib
import os
import re
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

    @staticmethod
    def _filename_component(value: str) -> str:
        """Keep metadata in the JSON; use a bounded, portable filename component."""
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Bundle topic and run ID must be nonempty strings")
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")[:48]
        if safe != value:
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
            return f"{safe or 'bundle'}_{digest}"
        return safe

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
        bundle_name = f"lec_bundle_{self._filename_component(topic)}_{self._filename_component(run_id)}"
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = Path(tmp_dir) / "bundle"
            bundle_dir.mkdir(parents=True)

            # 1. Copy main LEC object
            shutil.copy2(lec_path, bundle_dir / "lec_object.json")

            # 2. Copy artifacts referenced in LEC object
            self._copy_artifacts(lec_data, bundle_dir)

            # 3. Add METHODS.md
            if methods_path is not None:
                methods_path = Path(methods_path)
                if not methods_path.is_file():
                    raise FileNotFoundError(f"Methods file not found: {methods_path}")
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
        # Every nonempty reference is required; absent optional references are omitted.
        def safe_copy(src_str, dest_name):
            if not src_str:
                return
            src = Path(src_str)
            if not src.is_file():
                raise FileNotFoundError(f"Referenced artifact not found: {src}")
            shutil.copy2(src, dest_dir / dest_name)

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
        contents = "\n".join(f"- {path.name}" for path in sorted(bundle_dir.iterdir()) if path.is_file())
        content = f"""# LEC Bundle: {topic}
Run ID: {run_id}
Generated: {utc_now_iso()}

## Contents
{contents}
- .zenodo.json: Deposition metadata

## Usage
This bundle includes every artifact with a nonempty path referenced by the LEC object.
Packaging checks file presence; it does not certify scientific validity or reproducibility.
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
        """Replace the destination only after the complete archive is written."""
        with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix=".tmp", delete=False) as staged:
            staged_path = Path(staged.name)
        try:
            with zipfile.ZipFile(staged_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in sorted(source_dir.rglob("*")):
                    if file.is_file():
                        zf.write(file, file.relative_to(source_dir))
            os.replace(staged_path, output_path)
        finally:
            staged_path.unlink(missing_ok=True)
