from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backtesting.validation.look_ahead import LookAheadBiasCheck

_START = datetime(2026, 1, 1, tzinfo=UTC)


def test_chronologically_ordered_timestamps_pass() -> None:
    check = LookAheadBiasCheck()
    timestamps = [_START + timedelta(minutes=i) for i in range(10)]

    result = check.run(timestamps)

    assert result.passed is True
    assert result.detail["bars_checked"] == 10


def test_out_of_order_timestamp_fails_with_location() -> None:
    check = LookAheadBiasCheck()
    ordered = [_START + timedelta(minutes=i) for i in range(10)]
    out_of_order = ordered[:5] + [ordered[3]] + ordered[6:]

    result = check.run(out_of_order)

    assert result.passed is False
    assert result.detail["index"] == 5


def test_repeated_identical_timestamp_is_not_a_violation() -> None:
    # Two ticks at the exact same timestamp is normal (sub-second granularity
    # collapsed to a coarser clock); only a strict decrease is a violation.
    check = LookAheadBiasCheck()
    timestamps = [_START, _START, _START + timedelta(minutes=1)]

    result = check.run(timestamps)

    assert result.passed is True


def test_empty_sequence_passes() -> None:
    check = LookAheadBiasCheck()

    assert check.run([]).passed is True
