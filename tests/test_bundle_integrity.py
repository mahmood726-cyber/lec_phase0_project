"""Archive integrity fixtures; no scientific output is produced."""
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lec.publishing.zenodo import ZenodoPacker


def lec_file(tmp_path, **overrides):
    payload = {"question": {"title": "Software fixture"},
               "reproducibility": {"run_id": "fixture-run"}}
    payload.update(overrides)
    path = tmp_path / "lec.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("section", [
    {"evidence_universe": {"discovery_artifacts": [{"path": "missing-fixture.json"}]}},
    {"verification": {"truthcert": {"certificate": {"path": "missing-fixture.json"}}}},
    {"analysis": {"metaengine_contract": {"output": {"path": "missing-fixture.json"}}}},
    {"reproducibility": {"run_id": "fixture-run", "manifest": {"path": "missing-fixture.json"}}},
])
def test_missing_referenced_artifact_rejects_bundle(tmp_path, monkeypatch, section):
    monkeypatch.chdir(tmp_path)
    packer = ZenodoPacker(tmp_path / "release")
    with pytest.raises(FileNotFoundError):
        packer.pack(lec_file(tmp_path, **section))
    assert not list(packer.output_dir.glob("*.zip"))


def test_explicit_missing_methods_does_not_fall_back(tmp_path):
    with pytest.raises(FileNotFoundError):
        ZenodoPacker(tmp_path / "release").pack(
            lec_file(tmp_path), methods_path=tmp_path / "absent.md")


@pytest.mark.parametrize("run_id", ["nested/run", "run/../../escape"])
def test_metadata_cannot_create_nested_output_paths(tmp_path, run_id):
    packer = ZenodoPacker(tmp_path / "release")
    lec_path = lec_file(tmp_path, reproducibility={"run_id": run_id})
    output = packer.pack(lec_path, topic="drug / comparator: trial?")
    assert output.parent.resolve() == packer.output_dir.resolve()
    assert output.is_file()
    with zipfile.ZipFile(output) as archive:
        assert "lec_object.json" in archive.namelist()
        assert json.loads(archive.read("lec_object.json"))["reproducibility"]["run_id"] == run_id
        assert all("/" not in name and "\\" not in name for name in archive.namelist())


def test_archive_failure_preserves_existing_bundle(tmp_path, monkeypatch):
    packer = ZenodoPacker(tmp_path / "release")
    source = lec_file(tmp_path)
    output = packer.pack(source)
    before = output.read_bytes()
    original_write = zipfile.ZipFile.write
    calls = 0
    def failing_write(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("archive fixture failure")
        return original_write(self, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, "write", failing_write)
    with pytest.raises(OSError, match="archive fixture"):
        packer.pack(source)
    assert output.read_bytes() == before
    assert list(packer.output_dir.iterdir()) == [output]
