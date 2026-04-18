"""Core utilities: hashing, manifests, and schema validation."""

import hashlib
import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("lec")


def get_logger(name: str):
    """Get a named logger."""
    return logging.getLogger(f"lec.{name}")


def sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_string(data: str) -> str:
    """Compute SHA256 hash of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha1_string(data: str) -> str:
    """Compute SHA1 hash of a string (for LABEL: trial_key)."""
    return hashlib.sha1(data.encode("utf-8")).hexdigest()


def generate_run_id() -> str:
    """Generate unique run ID."""
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def utc_now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def load_schema(schema_path: Path) -> dict:
    """Load JSON schema from file."""
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_json(data: dict, schema: dict) -> tuple[bool, list[str]]:
    """Validate JSON data against schema. Returns (is_valid, errors)."""
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    if errors:
        return False, [f"{e.json_path}: {e.message}" for e in errors]
    return True, []


class LECEncoder(json.JSONEncoder):
    """Custom JSON encoder for LEC objects (handles Path)."""
    def default(self, obj):
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


def write_json(path: Path, data: dict, indent: int = 2) -> str:
    """Write JSON file and return its SHA256 hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=indent, cls=LECEncoder)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return sha256_string(content)


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class ManifestWriter:
    """Tracks artifacts and writes manifest file."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.artifacts: list[dict] = []
        self.created_at = utc_now_iso()

    def add_artifact(self, artifact_type: str, path: Path, sha256: str | None = None):
        """Add artifact to manifest."""
        if sha256 is None:
            sha256 = sha256_file(path)
        self.artifacts.append({
            "type": artifact_type,
            "path": str(path),
            "sha256": sha256,
            "added_at": utc_now_iso()
        })

    def write(self, output_path: Path) -> str:
        """Write manifest file and return its SHA256."""
        manifest = {
            "run_id": self.run_id,
            "created_at_utc": self.created_at,
            "completed_at_utc": utc_now_iso(),
            "artifacts": self.artifacts
        }
        return write_json(output_path, manifest)

    def to_dict(self) -> dict:
        """Return manifest as dictionary."""
        return {
            "run_id": self.run_id,
            "created_at_utc": self.created_at,
            "artifacts": self.artifacts
        }


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe for use as a filename."""
    import re
    # Replace any character that isn't alphanumeric, dash, underscore, or dot with underscore
    s = re.sub(r'[^\w\-.]', '_', name)
    return s.strip('_')


def make_trial_key(nct_id: str = None, pmid: str = None,
                   doi: str = None, raw_label: str = None) -> str:
    """Generate canonical trial_key according to guardrails."""
    if nct_id:
        return f"NCT:{nct_id.replace('NCT', '')}"
    if pmid:
        return f"PMID:{pmid}"
    if doi:
        return f"DOI:{doi}"
    if raw_label:
        return f"LABEL:{sha1_string(raw_label)}"
    raise ValueError("At least one identifier required for trial_key")
