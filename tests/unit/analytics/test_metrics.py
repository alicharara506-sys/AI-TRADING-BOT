from __future__ import annotations

import math

import pytest

from analytics import metrics

# Verified empirically (and independently cross-checked against raw numpy
# computations) for this exact alternating-return series.
_RETURNS = [10, -5, 10, -5, 10, -5, 10, -5]


def test_total_return() -> None:
    assert metrics.total_return(_RETURNS) == pytest.approx(20.0)


def test_max_drawdown() -> None:
    assert metrics.max_drawdown(_RETURNS) == pytest.approx(5.0)


def test_sharpe_ratio() -> None:
    assert metrics.sharpe_ratio(_RETURNS) == pytest.approx(0.3118047822311618)


def test_sortino_ratio() -> None:
    assert metrics.sortino_ratio(_RETURNS) == pytest.approx(0.5)


def test_calmar_ratio() -> None:
    assert metrics.calmar_ratio(_RETURNS) == pytest.approx(0.5)


def test_profit_factor() -> None:
    assert metrics.profit_factor(_RETURNS) == pytest.approx(2.0)


def test_expectancy_matches_mean_return() -> None:
    assert metrics.expectancy(_RETURNS) == pytest.approx(2.5)
    assert metrics.expectancy(_RETURNS) == pytest.approx(sum(_RETURNS) / len(_RETURNS))


def test_system_quality_number() -> None:
    assert metrics.system_quality_number(_RETURNS) == pytest.approx(0.881917103688197)


def test_value_at_risk_and_conditional_value_at_risk() -> None:
    assert metrics.value_at_risk(_RETURNS, confidence=0.95) == pytest.approx(5.0)
    assert metrics.conditional_value_at_risk(_RETURNS, confidence=0.95) == pytest.approx(5.0)


def test_empty_returns_rejected_everywhere() -> None:
    with pytest.raises(ValueError):
        metrics.total_return([])
    with pytest.raises(ValueError):
        metrics.sharpe_ratio([])


def test_profit_factor_no_losses_is_infinite() -> None:
    assert metrics.profit_factor([5.0, 10.0, 15.0]) == math.inf


def test_profit_factor_no_wins_is_zero() -> None:
    assert metrics.profit_factor([-5.0, -10.0]) == pytest.approx(0.0)


def test_zero_variance_returns_yield_zero_ratios_not_errors() -> None:
    assert metrics.sharpe_ratio([3.0, 3.0, 3.0]) == pytest.approx(0.0)
    assert metrics.sortino_ratio([3.0, 3.0, 3.0]) == pytest.approx(0.0)
    assert metrics.calmar_ratio([3.0, 3.0, 3.0]) == pytest.approx(0.0)
    assert metrics.system_quality_number([3.0, 3.0, 3.0]) == pytest.approx(0.0)


def test_invalid_confidence_rejected() -> None:
    with pytest.raises(ValueError):
        metrics.value_at_risk([1.0, 2.0], confidence=1.5)
    with pytest.raises(ValueError):
        metrics.conditional_value_at_risk([1.0, 2.0], confidence=0.0)


def test_annualization_scales_sharpe_by_sqrt_periods() -> None:
    base = metrics.sharpe_ratio(_RETURNS, periods_per_year=1.0)
    annualized = metrics.sharpe_ratio(_RETURNS, periods_per_year=252.0)

    assert annualized == pytest.approx(base * math.sqrt(252.0))
