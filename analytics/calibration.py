"""Confidence calibration: does a module's stated confidence actually track
its real win rate? A module that's right 90% of the time when it says
"90% confidence" is well-calibrated; one that's right 60% of the time when
it says "90% confidence" is systematically overconfident. This is the
standard reliability-diagram / Expected Calibration Error (ECE) technique
from probabilistic forecasting, computed here from real recorded
(confidence, outcome) pairs -- never a fabricated calibration score.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    """One confidence bucket (e.g. [0.7, 0.8)): the mean confidence the
    module actually stated for outcomes landing in this bucket, versus the
    real fraction of those outcomes that won.
    """

    lower: float
    upper: float
    predicted_mean_confidence: float
    actual_win_rate: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """buckets are sorted by confidence range, low to high; a perfectly
    calibrated module has predicted_mean_confidence == actual_win_rate in
    every bucket, and expected_calibration_error == 0.0.
    """

    module_name: str
    buckets: tuple[CalibrationBucket, ...]
    expected_calibration_error: float
    sample_count: int

    def render(self) -> str:
        lines = [
            f"Calibration report: {self.module_name} "
            f"(ECE={self.expected_calibration_error:.3f}, n={self.sample_count})"
        ]
        for bucket in self.buckets:
            lines.append(
                f"  [{bucket.lower:.1f}, {bucket.upper:.1f}): "
                f"predicted {bucket.predicted_mean_confidence * 100:.1f}%, "
                f"actual {bucket.actual_win_rate * 100:.1f}% "
                f"({bucket.sample_count} samples)"
            )
        return "\n".join(lines)


class ConfidenceCalibrationTracker:
    """Records (confidence, won) observations per module and computes a
    CalibrationReport on demand -- deliberately separate from
    HistoricalHitRateStore, which only ever tracked win/loss booleans, not
    the confidence value a module stated at the time. Extending that store
    to also carry confidence would have changed its existing contract;
    this is a new, focused component instead.
    """

    def __init__(self, *, num_buckets: int = 10) -> None:
        if num_buckets < 1:
            raise ValueError("num_buckets must be >= 1")
        self._num_buckets = num_buckets
        self._observations: dict[str, list[tuple[float, bool]]] = {}

    def record_outcome(self, module_name: str, *, confidence: float, won: bool) -> None:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0.0, 1.0]")
        self._observations.setdefault(module_name, []).append((confidence, won))

    def report(self, module_name: str) -> CalibrationReport | None:
        """None if no outcomes have been recorded for this module yet --
        there is nothing honest to report."""
        observations = self._observations.get(module_name)
        if not observations:
            return None

        bucket_width = 1.0 / self._num_buckets
        buckets: list[CalibrationBucket] = []
        total_absolute_error = 0.0
        n = len(observations)

        for index in range(self._num_buckets):
            lower = index * bucket_width
            upper = lower + bucket_width
            is_last_bucket = index == self._num_buckets - 1
            in_bucket = [
                (confidence, won)
                for confidence, won in observations
                if lower <= confidence < upper or (is_last_bucket and confidence == upper)
            ]
            if not in_bucket:
                continue

            confidences = [confidence for confidence, _ in in_bucket]
            predicted_mean = sum(confidences) / len(confidences)
            actual_win_rate = sum(1 for _, won in in_bucket if won) / len(in_bucket)
            buckets.append(
                CalibrationBucket(
                    lower=lower,
                    upper=upper,
                    predicted_mean_confidence=predicted_mean,
                    actual_win_rate=actual_win_rate,
                    sample_count=len(in_bucket),
                )
            )
            total_absolute_error += abs(predicted_mean - actual_win_rate) * len(in_bucket)

        return CalibrationReport(
            module_name=module_name,
            buckets=tuple(buckets),
            expected_calibration_error=total_absolute_error / n,
            sample_count=n,
        )


__all__ = ["CalibrationBucket", "CalibrationReport", "ConfidenceCalibrationTracker"]
