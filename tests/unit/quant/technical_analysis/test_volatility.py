from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.technical_analysis.volatility import (
    AtrVolatilityBreakoutModule,
    compute_atr,
    compute_true_ranges,
)

_SYMBOL = Symbol(name="EURUSD")


def _context(ohlc: list[tuple[float, float, float, float]]) -> MarketContext:
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=0.0,
        )
        for i, (o, h, low, c) in enumerate(ohlc)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


# Verified empirically: 14 quiet bars (range ~0.002) establish a small ATR,
# then one large bullish/bearish expansion bar clears the 1.5x threshold.
_QUIET = [
    (1.10 + 0.0005 * i, 1.10 + 0.0005 * i + 0.001, 1.10 + 0.0005 * i - 0.001, 1.10 + 0.0005 * i)
    for i in range(14)
]
_BREAKOUT_UP = [*_QUIET, (1.107, 1.130, 1.106, 1.128)]
_BREAKOUT_DOWN = [*_QUIET, (1.107, 1.108, 1.085, 1.086)]
_NO_BREAKOUT = [*_QUIET, (1.1075, 1.1085, 1.1065, 1.108)]


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        AtrVolatilityBreakoutModule(period=1)
    with pytest.raises(ValueError):
        AtrVolatilityBreakoutModule(expansion_multiple=1.0)


def test_bullish_expansion_bar_emits_long_evidence() -> None:
    module = AtrVolatilityBreakoutModule(period=14, expansion_multiple=1.5)

    evidence = module.analyze(_context(_BREAKOUT_UP))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG
    assert evidence[0].rationale["expansion_ratio"] > 1.5


def test_bearish_expansion_bar_emits_short_evidence() -> None:
    module = AtrVolatilityBreakoutModule(period=14, expansion_multiple=1.5)

    evidence = module.analyze(_context(_BREAKOUT_DOWN))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT


def test_normal_range_bar_emits_no_evidence() -> None:
    module = AtrVolatilityBreakoutModule(period=14, expansion_multiple=1.5)

    assert module.analyze(_context(_NO_BREAKOUT)) == []


def test_too_few_bars_emits_no_evidence() -> None:
    module = AtrVolatilityBreakoutModule(period=14, expansion_multiple=1.5)

    assert module.analyze(_context(_QUIET[:5])) == []


def test_compute_true_ranges_matches_hand_computed_values() -> None:
    bars = _context(
        [(1.10, 1.10, 1.10, 1.10), (1.10, 1.12, 1.09, 1.11), (1.11, 1.13, 1.10, 1.12)]
    ).bars

    true_ranges = compute_true_ranges(bars)

    assert true_ranges == pytest.approx([0.03, 0.03])


def test_compute_atr_is_the_inclusive_trailing_average() -> None:
    bars = _context(
        [
            (1.10, 1.10, 1.10, 1.10),
            (1.10, 1.12, 1.09, 1.11),  # TR = 0.03
            (1.11, 1.13, 1.10, 1.12),  # TR = 0.03
            (1.12, 1.15, 1.11, 1.14),  # TR = 0.04
        ]
    ).bars

    atr = compute_atr(bars, period=3)

    assert atr == pytest.approx((0.03 + 0.03 + 0.04) / 3)


def test_compute_atr_returns_none_with_insufficient_bars() -> None:
    bars = _context([(1.10, 1.10, 1.10, 1.10), (1.10, 1.12, 1.09, 1.11)]).bars

    assert compute_atr(bars, period=5) is None
