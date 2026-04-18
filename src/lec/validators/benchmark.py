"""Benchmark Validator.

Validates pipeline pooled estimates against gold-standard manual results
(e.g., published meta-analyses or metafor/R results).
"""

from lec.validators.base import BaseValidator
from typing import Dict, Any

class BenchmarkValidator(BaseValidator):
    """Validates pooled estimates against benchmarks."""

    name = "benchmark"
    description = "Validates results against gold-standard benchmarks"

    def validate(self, pooled_result: Dict[str, Any], benchmark: Dict[str, Any]) -> dict:
        """Compare pooled result against benchmark.
        
        Args:
            pooled_result: Result from meta-analysis (estimate, ci_low, ci_high)
            benchmark: Gold standard values
        """
        issues = []
        
        target = benchmark.get("estimate")
        actual = pooled_result.get("estimate")
        
        if target is not None and actual is not None:
            diff = abs(target - actual)
            # Threshold: 2% difference or 0.02 absolute
            if diff > 0.02 and diff / target > 0.02:
                issues.append(self._make_issue(
                    "pooled", "estimate",
                    f"Benchmark mismatch: actual={actual:.4f}, expected={target:.4f} (diff={diff:.4f})",
                    severity="error",
                    details={"actual": actual, "expected": target}
                ))
        
        # Check I2
        target_i2 = benchmark.get("i2")
        actual_i2 = pooled_result.get("heterogeneity", {}).get("i2")
        
        if target_i2 is not None and actual_i2 is not None:
            if abs(target_i2 - actual_i2) > 5: # 5% absolute diff
                issues.append(self._make_issue(
                    "pooled", "i2",
                    f"Heterogeneity mismatch: actual={actual_i2:.1f}%, expected={target_i2:.1f}%",
                    severity="warning"
                ))

        status = "FAIL" if any(i["severity"] == "error" for i in issues) else "PASS"
        if status == "PASS" and issues:
            status = "FLAG"
            
        return self._make_result(status, issues)
