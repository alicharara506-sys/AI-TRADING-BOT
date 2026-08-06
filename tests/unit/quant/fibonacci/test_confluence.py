from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.fibonacci.confluence import FibonacciConfluenceModule

_SYMBOL = Symbol(name="EURUSD")


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


# Verified empirically: swing low 1.00 (index 3) -> swing high 1.20 (index 10),
# then a pullback landing at the 61.8% retracement (1.0764) on the final bar.
_UP_IMPULSE_TO_618 = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17,
    1.20, 1.18, 1.16, 1.14, 1.12, 1.10, 1.09, 1.076,
]
# Same shape, but the final bar sits near the swing high itself -- far from
# every retracement level.
_UP_IMPULSE_FAR_FROM_LEVEL = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17,
    1.20, 1.18, 1.16, 1.14, 1.12, 1.10, 1.09, 1.19,
]
# Mirror image: swing high 1.10 -> swing low 0.90, pullback up to the 61.8%
# retracement (1.0236).
_DOWN_IMPULSE_TO_618 = [
    1.00, 1.03, 1.06, 1.10, 1.08, 1.05, 1.02, 0.99, 0.96, 0.93,
    0.90, 0.92, 0.94, 0.96, 0.98, 1.00, 1.01, 1.024,
]


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        FibonacciConfluenceModule(swing_arm=0)
    with pytest.raises(ValueError):
        FibonacciConfluenceModule(tolerance=0.0)


def test_up_impulse_pullback_at_618_emits_long_evidence() -> None:
    module = FibonacciConfluenceModule(swing_arm=2, tolerance=0.03)

    evidence = module.analyze(_context(_UP_IMPULSE_TO_618))

    assert len(evidence) == 1
    item = evidence[0]
    assert item.source_module == "fibonacci_confluence"
    assert item.direction == Direction.LONG
    assert item.rationale["fib_ratio"] == pytest.approx(0.618)
    assert item.rationale["impulse_up"] is True
    assert item.supporting_data["swing_low"] == pytest.approx(1.00)
    assert item.supporting_data["swing_high"] == pytest.approx(1.20)
    assert 0.0 < item.confidence <= 1.0


def test_price_far_from_any_level_emits_no_evidence() -> None:
    module = FibonacciConfluenceModule(swing_arm=2, tolerance=0.03)

    assert module.analyze(_context(_UP_IMPULSE_FAR_FROM_LEVEL)) == []


def test_down_impulse_pullback_at_618_emits_short_evidence() -> None:
    module = FibonacciConfluenceModule(swing_arm=2, tolerance=0.03)

    evidence = module.analyze(_context(_DOWN_IMPULSE_TO_618))

    assert len(evidence) == 1
    item = evidence[0]
    assert item.direction == Direction.SHORT
    assert item.rationale["impulse_up"] is False


def test_too_few_bars_emits_no_evidence() -> None:
    module = FibonacciConfluenceModule(swing_arm=2, tolerance=0.03)

    assert module.analyze(_context([1.0, 1.01, 1.02])) == []


def test_closer_to_level_yields_higher_confidence() -> None:
    module = FibonacciConfluenceModule(swing_arm=2, tolerance=0.03)

    close_evidence = module.analyze(_context(_UP_IMPULSE_TO_618))
    # Nudge the final price slightly further from the 61.8% level (1.0764) while
    # staying inside tolerance (distance/range must stay <= 0.03).
    farther_prices = _UP_IMPULSE_TO_618[:-1] + [1.071]
    farther_evidence = module.analyze(_context(farther_prices))

    assert len(close_evidence) == 1
    assert len(farther_evidence) == 1
    assert close_evidence[0].confidence > farther_evidence[0].confidence
