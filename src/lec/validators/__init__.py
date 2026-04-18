"""MVP Validators for Phase 0 Bronze.

Five validators:
1. effect_direction - validates effect direction consistency
2. inconsistent_n - checks for N/events inconsistencies
3. units_timepoint - validates units and timepoints
4. duplicates - detects duplicate studies
5. extraction_accuracy - validates against gold-standard (optional)
"""

from lec.validators.effect_direction import EffectDirectionValidator
from lec.validators.inconsistent_n import InconsistentNValidator
from lec.validators.units_timepoint import UnitsTimepointValidator
from lec.validators.duplicates import DuplicatesValidator
from lec.validators.extraction_accuracy import ExtractionAccuracyValidator
from lec.validators.benchmark import BenchmarkValidator
from lec.core import utc_now_iso


ALL_VALIDATORS = [
    EffectDirectionValidator(),
    InconsistentNValidator(),
    UnitsTimepointValidator(),
    DuplicatesValidator(),
]

# BenchmarkValidator is run separately on analysis results, not extraction data
# Extended validators include accuracy check
EXTENDED_VALIDATORS = ALL_VALIDATORS + [
    ExtractionAccuracyValidator(),
]


def run_all_validators(extraction_data: dict) -> dict:
    """Run all 4 MVP validators and return consolidated report."""
    results = []
    passed = 0
    flagged = 0
    failed = 0

    for validator in ALL_VALIDATORS:
        result = validator.validate(extraction_data)
        results.append(result)

        if result["status"] == "PASS":
            passed += 1
        elif result["status"] == "FLAG":
            flagged += 1
        else:
            failed += 1

    return {
        "validation_run_at": utc_now_iso(),
        "validators_run": [v.name for v in ALL_VALIDATORS],
        "summary": {
            "total": len(ALL_VALIDATORS),
            "passed": passed,
            "flagged": flagged,
            "failed": failed
        },
        "results": results
    }


__all__ = [
    "EffectDirectionValidator",
    "InconsistentNValidator",
    "UnitsTimepointValidator",
    "DuplicatesValidator",
    "BenchmarkValidator",
    "run_all_validators",
    "ALL_VALIDATORS",
]
