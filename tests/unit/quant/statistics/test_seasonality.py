from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.statistics.seasonality import SeasonalityModule, compute_seasonal_bias

_SYMBOL = Symbol(name="EURUSD")

# 2026-01-05 is a Monday.
_BASE_MONDAY = datetime(2026, 1, 5, tzinfo=UTC)
assert _BASE_MONDAY.weekday() == 0


def _weekday_biased_bars(num_days: int) -> list[Bar]:
    """One daily bar per day for `num_days`: Monday's close-to-close return
    is always +2%, every other weekday is always -1% -- a clean, fully
    deterministic weekday bias to test compute_seasonal_bias/SeasonalityModule
    against.
    """
    bars = []
    close = 100.0
    for i in range(num_days):
        timestamp = _BASE_MONDAY + timedelta(days=i)
        weekday_return = 0.02 if timestamp.weekday() == 0 else -0.01
        if i > 0:
            close *= 1 + weekday_return
        bars.append(
            Bar(
                symbol=_SYMBOL,
                timeframe=Timeframe.D1,
                timestamp=timestamp,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1.0,
            )
        )
    return bars


def test_rejects_invalid_group_by() -> None:
    with pytest.raises(ValueError):
        compute_seasonal_bias(_weekday_biased_bars(10), group_by="month")  # type: ignore[arg-type]


def test_compute_seasonal_bias_isolates_the_monday_effect() -> None:
    num_days = 56
    bars = _weekday_biased_bars(num_days)
    expected_mondays = sum(
        1 for i in range(1, num_days) if (_BASE_MONDAY + timedelta(days=i)).weekday() == 0
    )

    bias = compute_seasonal_bias(bars, group_by="weekday")

    monday_mean, monday_count = bias[0]
    assert monday_mean == pytest.approx(0.02)
    assert monday_count == expected_mondays
    tuesday_mean, _tuesday_count = bias[1]
    assert tuesday_mean == pytest.approx(-0.01)


def test_seasonality_module_emits_long_evidence_on_the_biased_weekday() -> None:
    module = SeasonalityModule(
        group_by="weekday", min_samples=5, min_mean_return=0.005, scale_return=0.02
    )
    # 57 days after a Monday (index 56) is exactly 8 weeks later -> Monday.
    bars = _weekday_biased_bars(57)
    assert bars[-1].timestamp.weekday() == 0

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_seasonality_module_emits_short_evidence_on_a_non_biased_weekday() -> None:
    module = SeasonalityModule(
        group_by="weekday", min_samples=5, min_mean_return=0.005, scale_return=0.02
    )
    bars = _weekday_biased_bars(58)  # one day past Monday -> Tuesday
    assert bars[-1].timestamp.weekday() == 1

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT


def test_seasonality_module_emits_no_evidence_with_too_few_samples() -> None:
    module = SeasonalityModule(group_by="weekday", min_samples=20, min_mean_return=0.005)
    bars = _weekday_biased_bars(10)

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars))) == []


def test_seasonality_module_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        SeasonalityModule(min_samples=1)
    with pytest.raises(ValueError):
        SeasonalityModule(min_mean_return=-0.1)
    with pytest.raises(ValueError):
        SeasonalityModule(scale_return=0.0)
