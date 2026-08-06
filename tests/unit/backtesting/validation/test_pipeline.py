from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backtesting.validation.look_ahead import LookAheadBiasCheck
from backtesting.validation.monte_carlo import MonteCarloCheck
from backtesting.validation.pipeline import ValidationPipeline
from backtesting.validation.walk_forward import WalkForwardCheck

_ROBUST = [10, -4, 8, -3, 9, -5, 7, -2, 10, -4, 9, -5, 8, -3, 7, -4, 10, -2, 9, -3]
_OVERFIT = [10, 12, 11, 9, 10, 11, 12, 9, 10, 11, -8, -9, -7, -10, -8, -9, -7, -10, -9, -8]


def _pipeline() -> ValidationPipeline:
    # max_drawdown=30 verified empirically: _ROBUST's tail drawdown is ~25.05
    # with seed=1/500 iterations, comfortably under this limit.
    return ValidationPipeline(
        walk_forward=WalkForwardCheck(max_degradation=0.5),
        monte_carlo=MonteCarloCheck(max_drawdown=30.0, iterations=500, seed=1),
        look_ahead=LookAheadBiasCheck(),
    )


def test_all_checks_passing_yields_passing_report() -> None:
    pipeline = _pipeline()
    timestamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(20)]

    report = pipeline.run(
        strategy_name="steady_strategy", trade_returns=_ROBUST, bar_timestamps=timestamps
    )

    assert report.passed is True
    assert len(report.checks) == 3
    assert {check.name for check in report.checks} == {
        "walk_forward",
        "monte_carlo_drawdown",
        "look_ahead_bias",
    }


def test_one_failing_check_fails_the_whole_report() -> None:
    pipeline = _pipeline()
    timestamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(20)]

    report = pipeline.run(
        strategy_name="overfit_strategy", trade_returns=_OVERFIT, bar_timestamps=timestamps
    )

    assert report.passed is False
    assert "walk_forward" in report.failure_summary()


def test_look_ahead_violation_fails_the_whole_report_even_with_good_returns() -> None:
    pipeline = _pipeline()
    timestamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(20)]
    # Corrupt the data pipeline: swap two timestamps out of order.
    timestamps[5], timestamps[6] = timestamps[6], timestamps[5]

    report = pipeline.run(
        strategy_name="steady_strategy", trade_returns=_ROBUST, bar_timestamps=timestamps
    )

    assert report.passed is False
    assert "look_ahead_bias" in report.failure_summary()
