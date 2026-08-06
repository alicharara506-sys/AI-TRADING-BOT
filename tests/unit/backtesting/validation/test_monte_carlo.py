from __future__ import annotations

import pytest

from backtesting.validation.monte_carlo import MonteCarloCheck

# Verified empirically with seed=1: near-zero tail drawdown.
_STEADY = [5, 4, 6, 5, 4, 6, 5, 4, 6, 5, 4, 6, 5, 4, 6]
# Verified empirically with seed=1: tail drawdown ~145, far above a 20-limit.
_VOLATILE = [20, -15, 25, -30, 10, -20, 15, -25, 30, -10, 20, -30, 10, -15, 25]


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        MonteCarloCheck(max_drawdown=10.0, iterations=10)
    with pytest.raises(ValueError):
        MonteCarloCheck(max_drawdown=0.0)
    with pytest.raises(ValueError):
        MonteCarloCheck(max_drawdown=10.0, percentile=1.5)


def test_fewer_than_minimum_trades_fails() -> None:
    check = MonteCarloCheck(max_drawdown=10.0)

    result = check.run([1.0, 2.0, 3.0])

    assert result.passed is False
    assert "fewer than" in result.detail["reason"]


def test_steady_returns_stay_within_drawdown_limit() -> None:
    check = MonteCarloCheck(max_drawdown=20.0, iterations=500, seed=1)

    result = check.run(_STEADY)

    assert result.passed is True
    assert result.detail["tail_drawdown"] == pytest.approx(0.0)


def test_volatile_returns_exceed_drawdown_limit() -> None:
    check = MonteCarloCheck(max_drawdown=20.0, iterations=500, seed=1)

    result = check.run(_VOLATILE)

    assert result.passed is False
    assert result.detail["tail_drawdown"] > 20.0


def test_same_seed_is_deterministic() -> None:
    check_a = MonteCarloCheck(max_drawdown=20.0, iterations=200, seed=42)
    check_b = MonteCarloCheck(max_drawdown=20.0, iterations=200, seed=42)

    result_a = check_a.run(_VOLATILE)
    result_b = check_b.run(_VOLATILE)

    assert result_a.detail["tail_drawdown"] == result_b.detail["tail_drawdown"]
