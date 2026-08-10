from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Symbol, Timeframe
from quant.technical_analysis.regime import compute_atr_percentile_rank, compute_volatility_regime

_SYMBOL = Symbol(name="EURUSD")


def _bars_from_ranges(ranges: list[float]) -> list[Bar]:
    """Builds bars whose true ranges follow `ranges` exactly: each bar's
    high/low straddle a fixed midpoint by range/2, and close returns to the
    midpoint, so true range == the requested value at every step and ATR
    isn't muddied by any drift in price level.
    """
    bars = []
    price = 100.0
    for i, r in enumerate(ranges):
        bars.append(
            Bar(
                symbol=_SYMBOL,
                timeframe=Timeframe.M1,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
                open=price,
                high=price + r / 2,
                low=price - r / 2,
                close=price,
                volume=1.0,
            )
        )
    return bars


def test_rejects_invalid_construction_parameters() -> None:
    bars = _bars_from_ranges([1.0] * 30)
    with pytest.raises(ValueError):
        compute_volatility_regime(bars, atr_period=1)
    with pytest.raises(ValueError):
        compute_volatility_regime(bars, lookback=1)
    with pytest.raises(ValueError):
        compute_volatility_regime(bars, low_percentile=70.0, high_percentile=30.0)


def test_returns_none_with_insufficient_bars() -> None:
    bars = _bars_from_ranges([1.0] * 10)

    assert compute_volatility_regime(bars, atr_period=5, lookback=10) is None


def test_classifies_a_volatility_spike_as_high() -> None:
    ranges = [1.0] * 20 + [10.0]
    bars = _bars_from_ranges(ranges)

    regime = compute_volatility_regime(bars, atr_period=2, lookback=15)

    assert regime == "high"


def test_classifies_a_volatility_collapse_as_low() -> None:
    ranges = [10.0] * 20 + [0.1]
    bars = _bars_from_ranges(ranges)

    regime = compute_volatility_regime(bars, atr_period=2, lookback=15)

    assert regime == "low"


def test_classifies_constant_volatility_as_normal() -> None:
    ranges = [1.0] * 30
    bars = _bars_from_ranges(ranges)

    regime = compute_volatility_regime(bars, atr_period=2, lookback=15)

    assert regime == "normal"


def test_atr_percentile_rank_rejects_invalid_parameters() -> None:
    bars = _bars_from_ranges([1.0] * 30)
    with pytest.raises(ValueError):
        compute_atr_percentile_rank(bars, atr_period=1)
    with pytest.raises(ValueError):
        compute_atr_percentile_rank(bars, lookback=1)


def test_atr_percentile_rank_is_none_with_insufficient_bars() -> None:
    bars = _bars_from_ranges([1.0] * 10)

    assert compute_atr_percentile_rank(bars, atr_period=5, lookback=10) is None


def test_atr_percentile_rank_is_high_after_a_volatility_spike() -> None:
    ranges = [1.0] * 20 + [10.0]
    bars = _bars_from_ranges(ranges)

    rank = compute_atr_percentile_rank(bars, atr_period=2, lookback=15)

    assert rank is not None
    assert rank >= 67.0


def test_atr_percentile_rank_is_fifty_for_constant_volatility() -> None:
    bars = _bars_from_ranges([1.0] * 30)

    rank = compute_atr_percentile_rank(bars, atr_period=2, lookback=15)

    assert rank == pytest.approx(50.0)
