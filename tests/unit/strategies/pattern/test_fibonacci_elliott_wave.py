from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, Symbol, Timeframe, TradeSignal
from strategies.pattern.fibonacci_elliott_wave import FibonacciElliottWaveStrategy

_SYMBOL = Symbol(name="EURUSD")

# Same fixture verified in tests/unit/quant/price_action/test_elliott_wave.py:
# a structurally valid up-impulse whose wave2 (50%) and wave4 (50%)
# retracements and wave3 (2.0x) extension all fall within typical
# Fibonacci ranges.
_VALID_UP_IMPULSE_PIVOTS = [1.00, 1.10, 1.05, 1.25, 1.15, 1.23]
_VALID_DOWN_IMPULSE_PIVOTS = [1.25, 1.15, 1.20, 1.00, 1.10, 1.02]
# Structurally valid (satisfies all three objective rules) but wave2's
# retracement (0.04 / 0.20 = 20%) is below the typical 38.2% floor.
_ATYPICAL_RATIO_PIVOTS = [1.00, 1.20, 1.16, 1.40, 1.25, 1.50]


def _zigzag(pivots: list[float], *, steps: int = 4) -> list[float]:
    prices: list[float] = []
    for start, end in zip(pivots, pivots[1:], strict=False):
        for step in range(steps):
            prices.append(start + (end - start) * step / steps)
    prices.append(pivots[-1])
    return prices


def _impulse_prices(pivots: list[float]) -> list[float]:
    first, second = pivots[0], pivots[1]
    leads_up = second > first
    lead = [first + 0.04, first + 0.02] if leads_up else [first - 0.04, first - 0.02]

    last, second_last = pivots[-1], pivots[-2]
    trails_up = last > second_last
    trail = [last - 0.02, last - 0.04] if trails_up else [last + 0.02, last + 0.04]

    return lead + _zigzag(pivots) + trail


def _bars(prices: list[float]) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M15,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0.0,
        )
        for i, price in enumerate(prices)
    ]


def _feed(strategy: FibonacciElliottWaveStrategy, bars: list[Bar]) -> list[TradeSignal]:
    signals: list[TradeSignal] = []
    for bar in bars:
        signal = strategy.on_bar(bar)
        if signal is not None:
            signals.append(signal)
    return signals


def test_rejects_invalid_swing_arm() -> None:
    with pytest.raises(ValueError):
        FibonacciElliottWaveStrategy(swing_arm=0)


def test_rejects_too_small_a_lookback() -> None:
    with pytest.raises(ValueError):
        FibonacciElliottWaveStrategy(lookback=5)


def test_fades_a_completed_up_impulse_with_typical_ratios() -> None:
    strategy = FibonacciElliottWaveStrategy()
    bars = _bars(_impulse_prices(_VALID_UP_IMPULSE_PIVOTS))

    signals = _feed(strategy, bars)

    assert len(signals) == 1
    assert signals[0].direction is Direction.SHORT  # fades the up-impulse
    assert signals[0].evidence[0].rationale["event"] == "elliott_wave5_completion"


def test_fades_a_completed_down_impulse_with_typical_ratios() -> None:
    strategy = FibonacciElliottWaveStrategy()
    bars = _bars(_impulse_prices(_VALID_DOWN_IMPULSE_PIVOTS))

    signals = _feed(strategy, bars)

    assert len(signals) == 1
    assert signals[0].direction is Direction.LONG  # fades the down-impulse


def test_does_not_resignal_the_same_impulse_on_later_bars() -> None:
    strategy = FibonacciElliottWaveStrategy()
    bars = _bars(_impulse_prices(_VALID_UP_IMPULSE_PIVOTS))
    # A few extra flat bars after the impulse completes.
    extra = _bars([bars[-1].close] * 3)

    signals = _feed(strategy, bars + extra)

    assert len(signals) == 1


def test_structurally_valid_but_atypical_ratios_emits_no_signal() -> None:
    strategy = FibonacciElliottWaveStrategy()
    bars = _bars(_impulse_prices(_ATYPICAL_RATIO_PIVOTS))

    signals = _feed(strategy, bars)

    assert signals == []


def test_no_impulse_yet_emits_no_signal() -> None:
    strategy = FibonacciElliottWaveStrategy()
    bars = _bars([1.00, 1.01, 1.02, 1.03, 1.04])

    assert _feed(strategy, bars) == []
