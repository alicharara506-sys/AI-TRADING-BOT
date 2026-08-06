from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, Symbol, Timeframe
from strategies.simple.sma_crossover import SmaCrossoverStrategy

_SYMBOL = Symbol(name="EURUSD")

# Verified (not hand-derived) fast=2/slow=4 SMA crossover trace for this exact
# sequence: fast crosses above slow at index 4 (LONG), and back below at index 8
# (SHORT). See the trace this was derived from for the full fast/slow values.
_CLOSES = [1.00, 0.95, 0.90, 0.95, 1.05, 1.15, 1.25, 1.20, 1.10, 1.00, 0.90]


def _bar(close: float, index: int) -> Bar:
    return Bar(
        symbol=_SYMBOL,
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0,
    )


def test_rejects_fast_period_not_less_than_slow_period() -> None:
    with pytest.raises(ValueError):
        SmaCrossoverStrategy(fast_period=10, slow_period=10)


def test_no_signal_while_warming_up() -> None:
    strategy = SmaCrossoverStrategy(fast_period=2, slow_period=4)

    for i, close in enumerate(_CLOSES[:3]):
        assert strategy.on_bar(_bar(close, i)) is None


def test_emits_long_then_short_signal_on_crossovers() -> None:
    strategy = SmaCrossoverStrategy(fast_period=2, slow_period=4)

    signals = [(i, strategy.on_bar(_bar(close, i))) for i, close in enumerate(_CLOSES)]
    fired = [(i, signal) for i, signal in signals if signal is not None]

    assert [i for i, _ in fired] == [4, 8]
    assert fired[0][1].direction == Direction.LONG
    assert fired[1][1].direction == Direction.SHORT
    assert fired[0][1].symbol == _SYMBOL
    assert fired[0][1].evidence[0].source_module == "sma_crossover"
    assert fired[0][1].evidence[0].confidence == pytest.approx(1.0)


def test_exactly_equal_averages_do_not_flip_state() -> None:
    """Flat, repeated prices push fast and slow SMAs to the exact same float --
    that must not register as a crossover in either direction."""
    strategy = SmaCrossoverStrategy(fast_period=2, slow_period=3)

    signals = [strategy.on_bar(_bar(1.0, i)) for i in range(6)]

    assert all(signal is None for signal in signals)
