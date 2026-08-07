from __future__ import annotations

import pytest

from analytics.calibration import ConfidenceCalibrationTracker


def test_rejects_invalid_num_buckets() -> None:
    with pytest.raises(ValueError):
        ConfidenceCalibrationTracker(num_buckets=0)


def test_rejects_confidence_outside_unit_interval() -> None:
    tracker = ConfidenceCalibrationTracker()
    with pytest.raises(ValueError):
        tracker.record_outcome("m1", confidence=-0.1, won=True)
    with pytest.raises(ValueError):
        tracker.record_outcome("m1", confidence=1.1, won=True)


def test_report_is_none_for_a_module_with_no_recorded_outcomes() -> None:
    tracker = ConfidenceCalibrationTracker()

    assert tracker.report("never_recorded") is None


def test_perfectly_calibrated_module_has_zero_error() -> None:
    tracker = ConfidenceCalibrationTracker(num_buckets=10)
    # 10 outcomes at confidence 0.9, exactly 9 win -> actual win rate 0.9,
    # matching the mean stated confidence exactly.
    for i in range(10):
        tracker.record_outcome("m1", confidence=0.9, won=i < 9)

    report = tracker.report("m1")

    assert report is not None
    assert report.expected_calibration_error == pytest.approx(0.0)
    assert report.sample_count == 10
    assert len(report.buckets) == 1
    bucket = report.buckets[0]
    assert bucket.lower == pytest.approx(0.9)
    assert bucket.upper == pytest.approx(1.0)
    assert bucket.predicted_mean_confidence == pytest.approx(0.9)
    assert bucket.actual_win_rate == pytest.approx(0.9)
    assert bucket.sample_count == 10


def test_overconfident_module_has_positive_expected_calibration_error() -> None:
    tracker = ConfidenceCalibrationTracker(num_buckets=10)
    # Bucket [0.9, 1.0]: stated 0.95, only 90% actually win.
    for i in range(10):
        tracker.record_outcome("m1", confidence=0.95, won=i < 9)
    # Bucket [0.5, 0.6): stated 0.55, only 50% actually win.
    for i in range(10):
        tracker.record_outcome("m1", confidence=0.55, won=i < 5)

    report = tracker.report("m1")

    assert report is not None
    assert report.sample_count == 20
    assert len(report.buckets) == 2
    assert report.expected_calibration_error == pytest.approx(0.05)


def test_confidence_of_exactly_one_lands_in_the_final_bucket() -> None:
    tracker = ConfidenceCalibrationTracker(num_buckets=10)
    tracker.record_outcome("m1", confidence=1.0, won=True)

    report = tracker.report("m1")

    assert report is not None
    assert len(report.buckets) == 1
    assert report.buckets[0].lower == pytest.approx(0.9)
    assert report.buckets[0].upper == pytest.approx(1.0)


def test_modules_are_tracked_independently() -> None:
    tracker = ConfidenceCalibrationTracker(num_buckets=10)
    tracker.record_outcome("m1", confidence=0.9, won=True)
    tracker.record_outcome("m2", confidence=0.2, won=False)

    report1 = tracker.report("m1")
    report2 = tracker.report("m2")

    assert report1 is not None and report1.sample_count == 1
    assert report2 is not None and report2.sample_count == 1


def test_render_includes_module_name_and_ece() -> None:
    tracker = ConfidenceCalibrationTracker(num_buckets=10)
    tracker.record_outcome("m1", confidence=0.9, won=True)

    rendered = tracker.report("m1").render()  # type: ignore[union-attr]

    assert "m1" in rendered
    assert "ECE=" in rendered
