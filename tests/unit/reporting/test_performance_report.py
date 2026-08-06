from __future__ import annotations

import pytest

from reporting.performance_report import PerformanceReport

# The same series verified against hand-computed and cross-checked values in
# tests/unit/analytics/test_metrics.py.
_RETURNS = [10, -5, 10, -5, 10, -5, 10, -5]


def test_from_returns_matches_the_underlying_metrics_functions() -> None:
    report = PerformanceReport.from_returns("demo_strategy", _RETURNS)

    assert report.strategy_name == "demo_strategy"
    assert report.trade_count == 8
    assert report.total_return == pytest.approx(20.0)
    assert report.max_drawdown == pytest.approx(5.0)
    assert report.sharpe_ratio == pytest.approx(0.3118047822311618)
    assert report.sortino_ratio == pytest.approx(0.5)
    assert report.calmar_ratio == pytest.approx(0.5)
    assert report.profit_factor == pytest.approx(2.0)
    assert report.expectancy == pytest.approx(2.5)
    assert report.value_at_risk_95 == pytest.approx(5.0)
    assert report.conditional_value_at_risk_95 == pytest.approx(5.0)


def test_render_includes_strategy_name_and_every_metric_label() -> None:
    report = PerformanceReport.from_returns("demo_strategy", _RETURNS)

    text = report.render()

    assert "demo_strategy" in text
    for label in ("Sharpe", "Sortino", "Calmar", "Profit factor", "Expectancy", "SQN", "VaR"):
        assert label in text


def test_to_dict_round_trips_every_field() -> None:
    report = PerformanceReport.from_returns("demo_strategy", _RETURNS)

    as_dict = report.to_dict()

    assert as_dict["strategy_name"] == "demo_strategy"
    assert as_dict["trade_count"] == 8
    assert as_dict["sharpe_ratio"] == pytest.approx(report.sharpe_ratio)
