from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.fibonacci.extensions import FibonacciExtensionModule, compute_fibonacci_extensions

_SYMBOL = Symbol(name="EURUSD")

# Deep low at index 3 (1.00), a sharp two-bar approach into a swing high at
# index 10 (1.20) that disqualifies the shallow "double dip" right after it
# from ever being confirmed as a newer swing low (index 9's 1.17 is lower
# than dip1's 1.18, and dip1 is in turn lower than dip2's 1.19 -- each dip
# bar is disqualified by a lower neighbor within its own confirmation
# window), so the (low=3, high=10) leg stays the most recently confirmed
# pair even as price resumes climbing well past the high.
_EXTENSION_SETUP_PRICES = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18, 1.19,
]


def _bars(prices: list[float]) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=p,
            high=p,
            low=p,
            close=p,
            volume=1.0,
        )
        for i, p in enumerate(prices)
    ]


def test_compute_fibonacci_extensions_projects_beyond_the_swing_high_going_up() -> None:
    levels = compute_fibonacci_extensions(1.00, 1.20, impulse_up=True)

    assert levels[1.618] == pytest.approx(1.00 + 1.618 * 0.20)
    assert all(level > 1.20 for level in levels.values())


def test_compute_fibonacci_extensions_projects_below_the_swing_low_going_down() -> None:
    levels = compute_fibonacci_extensions(1.00, 1.20, impulse_up=False)

    assert levels[1.618] == pytest.approx(1.20 - 1.618 * 0.20)
    assert all(level < 1.00 for level in levels.values())


def test_compute_fibonacci_extensions_rejects_a_degenerate_leg() -> None:
    with pytest.raises(ValueError):
        compute_fibonacci_extensions(1.20, 1.00, impulse_up=True)
    with pytest.raises(ValueError):
        compute_fibonacci_extensions(1.00, 1.00, impulse_up=True)


def test_module_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        FibonacciExtensionModule(swing_arm=0)
    with pytest.raises(ValueError):
        FibonacciExtensionModule(tolerance=0.0)


def test_module_emits_long_evidence_near_an_upside_extension_target() -> None:
    module = FibonacciExtensionModule(swing_arm=2, tolerance=0.03)
    prices = [*_EXTENSION_SETUP_PRICES, 1.22, 1.25, 1.30, 1.3236, 1.322]

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_bars(prices))))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG
    assert evidence[0].rationale["extension_ratio"] == pytest.approx(1.618)
    assert evidence[0].rationale["impulse_up"] is True


def test_module_emits_short_evidence_near_a_downside_extension_target() -> None:
    module = FibonacciExtensionModule(swing_arm=2, tolerance=0.03)
    prices = [2.0 - p for p in [*_EXTENSION_SETUP_PRICES, 1.22, 1.25, 1.30, 1.3236, 1.322]]

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_bars(prices))))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].rationale["impulse_up"] is False


def test_module_emits_no_evidence_between_extension_levels() -> None:
    module = FibonacciExtensionModule(swing_arm=2, tolerance=0.03)
    prices = [*_EXTENSION_SETUP_PRICES, 1.22]

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_bars(prices)))) == []


def test_module_emits_no_evidence_with_too_few_bars() -> None:
    module = FibonacciExtensionModule(swing_arm=2, tolerance=0.03)

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_bars([1.0, 1.1])))) == []
