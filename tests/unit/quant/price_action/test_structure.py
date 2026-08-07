from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.price_action.structure import (
    MarketStructureModule,
    compute_structure_invalidation_level,
)

_SYMBOL = Symbol(name="EURUSD")


def _zigzag(pivots: list[float], *, steps: int = 4) -> list[float]:
    prices: list[float] = []
    for start, end in zip(pivots, pivots[1:], strict=False):
        for step in range(steps):
            prices.append(start + (end - start) * step / steps)
    prices.append(pivots[-1])
    return prices


def _context(prices: list[float]) -> MarketContext:
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0.0,
        )
        for i, price in enumerate(prices)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


# Verified empirically: higher-highs/higher-lows structure (swings at 1.10,
# 1.03, 1.15, 1.06, 1.20), confirmed with enough trailing bars.
_UPTREND_STRUCTURE = _zigzag([1.00, 1.10, 1.03, 1.15, 1.06, 1.20, 1.12])
# Mirror: lower-highs/lower-lows.
_DOWNTREND_STRUCTURE = _zigzag([1.20, 1.10, 1.17, 1.05, 1.14, 1.00, 1.08])


def test_rejects_invalid_swing_arm() -> None:
    with pytest.raises(ValueError):
        MarketStructureModule(swing_arm=0)


def test_uptrend_bos_on_break_above_last_swing_high() -> None:
    module = MarketStructureModule(swing_arm=2)

    evidence = module.analyze(_context(_UPTREND_STRUCTURE + [1.25]))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG
    assert evidence[0].rationale["event"] == "bos_uptrend_continuation"


def test_uptrend_choch_on_break_below_last_swing_low() -> None:
    module = MarketStructureModule(swing_arm=2)

    evidence = module.analyze(_context(_UPTREND_STRUCTURE + [1.00]))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].rationale["event"] == "choch_uptrend_reversal"


def test_downtrend_bos_on_break_below_last_swing_low() -> None:
    module = MarketStructureModule(swing_arm=2)

    evidence = module.analyze(_context(_DOWNTREND_STRUCTURE + [0.95]))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].rationale["event"] == "bos_downtrend_continuation"


def test_downtrend_choch_on_break_above_last_swing_high() -> None:
    module = MarketStructureModule(swing_arm=2)

    evidence = module.analyze(_context(_DOWNTREND_STRUCTURE + [1.20]))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG
    assert evidence[0].rationale["event"] == "choch_downtrend_reversal"


def test_price_still_inside_the_range_emits_no_evidence() -> None:
    module = MarketStructureModule(swing_arm=2)

    assert module.analyze(_context(_UPTREND_STRUCTURE + [1.13])) == []


def test_too_few_confirmed_swings_emits_no_evidence() -> None:
    module = MarketStructureModule(swing_arm=2)

    assert module.analyze(_context([1.0, 1.01, 1.02, 1.03, 1.04])) == []


# -- compute_structure_invalidation_level -------------------------------------

_SWING_PRICES = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18, 1.16,
]


def test_invalidation_level_for_a_long_is_the_last_confirmed_swing_low() -> None:
    bars = _context(_SWING_PRICES).bars

    level = compute_structure_invalidation_level(bars, Direction.LONG, swing_arm=2)

    assert level == pytest.approx(1.00)


def test_invalidation_level_for_a_short_is_the_last_confirmed_swing_high() -> None:
    bars = _context(_SWING_PRICES).bars

    level = compute_structure_invalidation_level(bars, Direction.SHORT, swing_arm=2)

    assert level == pytest.approx(1.20)


def test_invalidation_level_is_none_for_a_neutral_direction() -> None:
    bars = _context(_SWING_PRICES).bars

    assert compute_structure_invalidation_level(bars, Direction.NEUTRAL, swing_arm=2) is None


def test_invalidation_level_is_none_without_a_confirmed_swing() -> None:
    bars = _context([1.0, 1.01, 1.02, 1.03, 1.04]).bars

    assert compute_structure_invalidation_level(bars, Direction.LONG, swing_arm=2) is None
