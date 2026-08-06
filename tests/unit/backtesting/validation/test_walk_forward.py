from __future__ import annotations

import pytest

from backtesting.validation.walk_forward import WalkForwardCheck

# Verified empirically: similar profile in both halves -> zero degradation.
_ROBUST = [10, -4, 8, -3, 9, -5, 7, -2, 10, -4, 9, -5, 8, -3, 7, -4, 10, -2, 9, -3]
# Great in-sample (all wins), terrible out-of-sample (all losses).
_OVERFIT = [10, 12, 11, 9, 10, 11, 12, 9, 10, 11, -8, -9, -7, -10, -8, -9, -7, -10, -9, -8]


def test_rejects_invalid_max_degradation() -> None:
    with pytest.raises(ValueError):
        WalkForwardCheck(max_degradation=1.5)
    with pytest.raises(ValueError):
        WalkForwardCheck(max_degradation=-0.1)


def test_fewer_than_minimum_trades_fails() -> None:
    check = WalkForwardCheck()

    result = check.run([1.0, 2.0, 3.0])

    assert result.passed is False
    assert "fewer than" in result.detail["reason"]


def test_robust_strategy_with_no_degradation_passes() -> None:
    check = WalkForwardCheck(max_degradation=0.5)

    result = check.run(_ROBUST)

    assert result.passed is True
    assert result.detail["degradation"] == pytest.approx(0.0)


def test_overfit_strategy_with_severe_degradation_fails() -> None:
    check = WalkForwardCheck(max_degradation=0.5)

    result = check.run(_OVERFIT)

    assert result.passed is False
    assert result.detail["degradation"] > 0.5
    assert result.detail["out_of_sample_total_return"] < 0


def test_unprofitable_in_sample_passes_if_out_of_sample_not_worse() -> None:
    check = WalkForwardCheck()
    # In-sample already loses money; out-of-sample loses the same amount --
    # nothing to "degrade" from a baseline of zero or negative.
    trades = [-1.0] * 10 + [-1.0] * 10

    result = check.run(trades)

    assert result.passed is True
