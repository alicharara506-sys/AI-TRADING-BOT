from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.technical_analysis.momentum import (
    AdxTrendModule,
    MacdCrossoverModule,
    compute_adx,
    compute_macd,
)

_SYMBOL = Symbol(name="EURUSD")


def _bars(ohlc: list[tuple[float, float, float, float]]) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=1.0,
        )
        for i, (o, h, low, c) in enumerate(ohlc)
    ]


def _flat_bars(closes: list[float]) -> list[Bar]:
    return _bars([(c, c, c, c) for c in closes])


def _reference_ema(values: list[float], period: int) -> list[float]:
    alpha = 2.0 / (period + 1)
    ema = values[0]
    result = [ema]
    for value in values[1:]:
        ema = alpha * value + (1 - alpha) * ema
        result.append(ema)
    return result


# -- MACD --------------------------------------------------------------------


def test_compute_macd_matches_a_reference_ema_implementation() -> None:
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    bars = _flat_bars(closes)

    result = compute_macd(bars, fast_period=2, slow_period=3, signal_period=2)

    assert result is not None
    fast = _reference_ema(closes, 2)
    slow = _reference_ema(closes, 3)
    macd_line = [f - s for f, s in zip(fast, slow, strict=True)]
    signal_line = _reference_ema(macd_line, 2)
    expected_histogram = macd_line[-1] - signal_line[-1]

    macd, signal, histogram = result
    assert macd == pytest.approx(macd_line[-1])
    assert signal == pytest.approx(signal_line[-1])
    assert histogram == pytest.approx(expected_histogram)


def test_compute_macd_rejects_invalid_periods() -> None:
    bars = _flat_bars([1.0] * 40)
    with pytest.raises(ValueError):
        compute_macd(bars, fast_period=26, slow_period=12)
    with pytest.raises(ValueError):
        compute_macd(bars, fast_period=0)


def test_compute_macd_returns_none_with_insufficient_bars() -> None:
    bars = _flat_bars([1.0] * 4)

    assert compute_macd(bars, fast_period=2, slow_period=3, signal_period=2) is None


def _first_crossover_bars(closes: list[float], *, fast: int, slow: int, signal: int) -> list[Bar]:
    """Truncates `closes` to the shortest prefix whose MACD histogram has
    flipped sign relative to the previous bar -- i.e. the exact prefix
    MacdCrossoverModule should fire on. Fails the test via the final assert
    if the series never crosses.
    """
    bars = _flat_bars(closes)
    previous_histogram: float | None = None
    for end in range(fast + slow, len(bars) + 1):
        result = compute_macd(bars[:end], fast_period=fast, slow_period=slow, signal_period=signal)
        if result is None:
            continue
        histogram = result[2]
        if previous_histogram is not None and (
            (previous_histogram <= 0 < histogram) or (previous_histogram >= 0 > histogram)
        ):
            return bars[:end]
        previous_histogram = histogram
    raise AssertionError("series never produced a MACD histogram sign flip")


def test_macd_crossover_module_detects_bullish_crossover() -> None:
    closes = [1.10 - 0.003 * i for i in range(1, 15)] + [1.10 + 0.01 * i for i in range(1, 15)]
    bars = _first_crossover_bars(closes, fast=3, slow=6, signal=3)
    module = MacdCrossoverModule(fast_period=3, slow_period=6, signal_period=3, atr_period=5)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_macd_crossover_module_detects_bearish_crossover() -> None:
    closes = [1.10 + 0.003 * i for i in range(1, 15)] + [1.10 - 0.01 * i for i in range(1, 15)]
    bars = _first_crossover_bars(closes, fast=3, slow=6, signal=3)
    module = MacdCrossoverModule(fast_period=3, slow_period=6, signal_period=3, atr_period=5)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT


def test_macd_crossover_module_emits_no_evidence_with_insufficient_bars() -> None:
    module = MacdCrossoverModule(fast_period=12, slow_period=26, signal_period=9)

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_flat_bars([1.0] * 10)))) == []


# -- ADX / DMI -----------------------------------------------------------------


def _trending_bars(count: int) -> list[Bar]:
    ohlc = [(9.5 + i, 10.0 + i, 9.0 + i, 9.7 + i) for i in range(count)]
    return _bars(ohlc)


def _ranging_bars(count: int) -> list[Bar]:
    ohlc = [
        (10.0, 10.2, 9.8, 10.0 + (0.05 if i % 2 == 0 else -0.05)) for i in range(count)
    ]
    return _bars(ohlc)


def test_compute_adx_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        compute_adx(_trending_bars(30), period=1)


def test_compute_adx_returns_none_with_insufficient_bars() -> None:
    assert compute_adx(_trending_bars(10), period=14) is None


def test_compute_adx_is_strong_and_bullish_in_a_clean_uptrend() -> None:
    result = compute_adx(_trending_bars(30), period=5)

    assert result is not None
    plus_di, minus_di, adx = result
    assert plus_di > minus_di
    assert adx > 50.0


def test_compute_adx_is_weak_in_a_ranging_market() -> None:
    result = compute_adx(_ranging_bars(30), period=5)

    assert result is not None
    _plus_di, _minus_di, adx = result
    assert adx < 25.0


def test_adx_trend_module_emits_long_evidence_in_a_strong_uptrend() -> None:
    module = AdxTrendModule(period=5, trend_threshold=25.0)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_trending_bars(30))))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_adx_trend_module_emits_no_evidence_in_a_ranging_market() -> None:
    module = AdxTrendModule(period=5, trend_threshold=25.0)

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_ranging_bars(30)))) == []


def test_adx_trend_module_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        AdxTrendModule(period=1)
    with pytest.raises(ValueError):
        AdxTrendModule(trend_threshold=0.0)
    with pytest.raises(ValueError):
        AdxTrendModule(trend_threshold=100.0)
