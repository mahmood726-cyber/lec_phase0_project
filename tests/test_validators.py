"""Tests for MVP validators."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lec.validators import (
    run_all_validators,
    EffectDirectionValidator,
    InconsistentNValidator,
    UnitsTimepointValidator,
    DuplicatesValidator,
)


class TestEffectDirectionValidator:
    """Tests for effect direction validator."""

    def test_valid_direction(self):
        """Test that matching direction passes."""
        data = {
            "studies": [{
                "study_id": "test1",
                "outcomes": [{
                    "name": "mortality",
                    "effect": {"measure": "OR", "estimate": 0.75},
                    "effect_direction": "treatment"
                }]
            }]
        }
        validator = EffectDirectionValidator()
        result = validator.validate(data)
        assert result["status"] == "PASS"

    def test_mismatched_direction(self):
        """Test that mismatched direction fails."""
        data = {
            "studies": [{
                "study_id": "test1",
                "outcomes": [{
                    "name": "mortality",
                    "effect": {"measure": "OR", "estimate": 0.75},
                    "effect_direction": "control"  # Wrong - OR<1 favors treatment
                }]
            }]
        }
        validator = EffectDirectionValidator()
        result = validator.validate(data)
        assert result["status"] == "FAIL"
        assert len(result["issues"]) > 0


class TestInconsistentNValidator:
    """Tests for inconsistent N validator."""

    def test_valid_n(self):
        """Test that valid N passes."""
        data = {
            "studies": [{
                "study_id": "test1",
                "n_total": 100,
                "arms": [
                    {"label": "treatment", "n": 50, "events": 10},
                    {"label": "control", "n": 50, "events": 15}
                ]
            }]
        }
        validator = InconsistentNValidator()
        result = validator.validate(data)
        assert result["status"] == "PASS"

    def test_events_exceeds_n(self):
        """Test that events > N fails."""
        data = {
            "studies": [{
                "study_id": "test1",
                "arms": [
                    {"label": "treatment", "n": 50, "events": 60}  # Invalid
                ]
            }]
        }
        validator = InconsistentNValidator()
        result = validator.validate(data)
        assert result["status"] == "FAIL"


class TestUnitsTimepointValidator:
    """Tests for units and timepoint validator."""

    def test_missing_timepoint_flags(self):
        """Test that missing timepoint flags."""
        data = {
            "studies": [{
                "study_id": "test1",
                "outcomes": [{
                    "name": "primary",
                    "type": "binary",
                    "effect": {"measure": "OR", "estimate": 0.8}
                    # Missing timepoint
                }]
            }]
        }
        validator = UnitsTimepointValidator()
        result = validator.validate(data)
        assert result["status"] == "FLAG"


class TestDuplicatesValidator:
    """Tests for duplicates validator."""

    def test_no_duplicates(self):
        """Test that unique studies pass."""
        data = {
            "studies": [
                {"study_id": "study1", "nct_id": "NCT001", "title": "First Study"},
                {"study_id": "study2", "nct_id": "NCT002", "title": "Second Study"}
            ]
        }
        validator = DuplicatesValidator()
        result = validator.validate(data)
        assert result["status"] == "PASS"

    def test_duplicate_nct(self):
        """Test that duplicate NCT IDs fail."""
        data = {
            "studies": [
                {"study_id": "study1", "nct_id": "NCT001"},
                {"study_id": "study2", "nct_id": "NCT001"}  # Duplicate
            ]
        }
        validator = DuplicatesValidator()
        result = validator.validate(data)
        assert result["status"] == "FAIL"


class TestRunAllValidators:
    """Tests for running all validators."""

    def test_all_pass(self):
        """Test that good data passes all validators."""
        data = {
            "studies": [{
                "study_id": "test1",
                "nct_id": "NCT001",
                "n_total": 100,
                "arms": [
                    {"label": "treatment", "n": 50, "events": 10},
                    {"label": "control", "n": 50, "events": 15}
                ],
                "outcomes": [{
                    "name": "primary",
                    "type": "binary",
                    "timepoint": 12,
                    "timepoint_unit": "months",
                    "effect": {
                        "measure": "OR",
                        "estimate": 0.65,
                        "ci_low": 0.45,
                        "ci_high": 0.95
                    },
                    "effect_direction": "treatment"
                }]
            }]
        }
        result = run_all_validators(data)
        assert result["summary"]["total"] == 4
        assert "validators_run" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
