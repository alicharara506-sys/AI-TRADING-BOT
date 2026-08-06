from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.interfaces.types import Bar, Symbol, Timeframe
from quant.price_action.swings import find_all_swing_points, find_last_swings

_SYMBOL = Symbol(name="EURUSD")


def _bars(prices: list[float]) -> list[Bar]:
    return [
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
    ]


def test_finds_low_then_high_in_an_up_impulse() -> None:
    # Verified in the Fibonacci module's own tests: swing low at index 3
    # (1.00), swing high at index 10 (1.20).
    prices = [1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18, 1.16]
    bars = _bars(prices)

    low_index, high_index = find_last_swings(bars, arm=2)

    assert low_index == 3
    assert high_index == 10


def test_flat_data_ties_low_and_high_at_the_same_index() -> None:
    # On perfectly flat data every bar ties for "the extreme within its
    # window" under the fractal definition, so this legitimately returns a
    # real (tied) index rather than None -- degenerate-leg handling (e.g.
    # Fibonacci's leg_range <= 0 check) lives in the consumer, not here.
    bars = _bars([1.0] * 10)

    low_index, high_index = find_last_swings(bars, arm=2)

    assert low_index == high_index
    assert low_index is not None


def test_too_few_bars_for_the_arm_finds_no_swings() -> None:
    bars = _bars([1.0, 1.1, 1.2])

    low_index, high_index = find_last_swings(bars, arm=2)

    assert low_index is None
    assert high_index is None


def test_find_all_swing_points_returns_chronological_tagged_sequence() -> None:
    prices = [1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18, 1.16]
    bars = _bars(prices)

    points = find_all_swing_points(bars, arm=2)

    indices = [index for index, _kind in points]
    assert indices == sorted(indices)  # chronological order
    assert (3, "low") in points
    assert (10, "high") in points
