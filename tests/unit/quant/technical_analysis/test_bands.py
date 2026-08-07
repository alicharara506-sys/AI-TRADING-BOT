from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.technical_analysis.bands import (
    BollingerBandModule,
    DonchianBreakoutModule,
    KeltnerChannelModule,
    compute_bollinger_bands,
    compute_donchian_channels,
    compute_keltner_channels,
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


# -- Bollinger -----------------------------------------------------------------


def test_compute_bollinger_bands_matches_hand_computed_values() -> None:
    closes = [10.0] * 9 + [20.0]
    bars = _flat_bars(closes)

    result = compute_bollinger_bands(bars, period=10, num_std=2.0)

    assert result is not None
    mean, upper, lower = result
    assert mean == pytest.approx(11.0)
    assert upper == pytest.approx(17.0)
    assert lower == pytest.approx(5.0)


def test_compute_bollinger_bands_rejects_invalid_parameters() -> None:
    bars = _flat_bars([1.0] * 30)
    with pytest.raises(ValueError):
        compute_bollinger_bands(bars, period=1)
    with pytest.raises(ValueError):
        compute_bollinger_bands(bars, num_std=0.0)


def test_compute_bollinger_bands_returns_none_with_insufficient_bars() -> None:
    assert compute_bollinger_bands(_flat_bars([1.0] * 5), period=10) is None


def test_bollinger_module_emits_short_evidence_above_the_upper_band() -> None:
    closes = [10.0] * 9 + [20.0]
    module = BollingerBandModule(period=10, num_std=2.0)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_flat_bars(closes))))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT


def test_bollinger_module_emits_long_evidence_below_the_lower_band() -> None:
    closes = [10.0] * 9 + [0.0]
    module = BollingerBandModule(period=10, num_std=2.0)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_flat_bars(closes))))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_bollinger_module_emits_no_evidence_inside_the_bands() -> None:
    module = BollingerBandModule(period=10, num_std=2.0)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_flat_bars([10.0] * 10))))

    assert evidence == []


# -- Keltner ---------------------------------------------------------------


def _quiet_then_breakout_bars(*, breakout_close: float) -> list[Bar]:
    quiet = [
        (
            10.0 + 0.01 * (i % 2),
            10.05 + 0.01 * (i % 2),
            9.95 + 0.01 * (i % 2),
            10.0 + 0.01 * (i % 2),
        )
        for i in range(20)
    ]
    breakout = (
        10.0,
        max(10.0, breakout_close) + 0.1,
        min(10.0, breakout_close) - 0.1,
        breakout_close,
    )
    return _bars([*quiet, breakout])


def test_compute_keltner_channels_rejects_invalid_parameters() -> None:
    bars = _quiet_then_breakout_bars(breakout_close=10.0)
    with pytest.raises(ValueError):
        compute_keltner_channels(bars, period=0)
    with pytest.raises(ValueError):
        compute_keltner_channels(bars, multiplier=0.0)


def test_compute_keltner_channels_returns_none_with_insufficient_bars() -> None:
    assert compute_keltner_channels(_flat_bars([1.0] * 3), period=10) is None


def test_keltner_module_emits_long_evidence_on_an_upside_breakout() -> None:
    module = KeltnerChannelModule(period=10, atr_period=5, multiplier=2.0)
    bars = _quiet_then_breakout_bars(breakout_close=15.0)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_keltner_module_emits_short_evidence_on_a_downside_breakout() -> None:
    module = KeltnerChannelModule(period=10, atr_period=5, multiplier=2.0)
    bars = _quiet_then_breakout_bars(breakout_close=5.0)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT


def test_keltner_module_emits_no_evidence_within_the_channel() -> None:
    module = KeltnerChannelModule(period=10, atr_period=5, multiplier=2.0)
    bars = _quiet_then_breakout_bars(breakout_close=10.0)

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars))) == []


# -- Donchian ----------------------------------------------------------------


def test_compute_donchian_channels_matches_hand_computed_values() -> None:
    bars = _bars([(1.0, 1.0 + 0.1 * i, 1.0 - 0.1 * i, 1.0) for i in range(10)])

    result = compute_donchian_channels(bars, period=10)

    assert result is not None
    upper, lower = result
    assert upper == pytest.approx(1.0 + 0.1 * 9)
    assert lower == pytest.approx(1.0 - 0.1 * 9)


def test_compute_donchian_channels_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        compute_donchian_channels(_flat_bars([1.0] * 5), period=0)


def test_compute_donchian_channels_returns_none_with_insufficient_bars() -> None:
    assert compute_donchian_channels(_flat_bars([1.0] * 3), period=10) is None


def test_donchian_module_emits_long_evidence_on_a_new_high_breakout() -> None:
    module = DonchianBreakoutModule(period=10)
    channel_bars = _bars([(1.0, 1.0 + 0.01 * i, 1.0 - 0.01 * i, 1.0) for i in range(10)])
    breakout_bar = _bars([(1.0, 1.5, 1.0, 1.5)])
    bars = channel_bars + breakout_bar

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_donchian_module_emits_short_evidence_on_a_new_low_breakout() -> None:
    module = DonchianBreakoutModule(period=10)
    channel_bars = _bars([(1.0, 1.0 + 0.01 * i, 1.0 - 0.01 * i, 1.0) for i in range(10)])
    breakout_bar = _bars([(1.0, 1.0, 0.5, 0.5)])
    bars = channel_bars + breakout_bar

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT


def test_donchian_module_emits_no_evidence_within_the_channel() -> None:
    module = DonchianBreakoutModule(period=10)
    channel_bars = _bars([(1.0, 1.0 + 0.01 * i, 1.0 - 0.01 * i, 1.0) for i in range(10)])
    inside_bar = _bars([(1.0, 1.05, 0.95, 1.0)])

    evidence = module.analyze(
        MarketContext(symbol=_SYMBOL, bars=tuple(channel_bars + inside_bar))
    )

    assert evidence == []


def test_donchian_module_emits_no_evidence_with_too_few_bars() -> None:
    module = DonchianBreakoutModule(period=10)

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_flat_bars([1.0] * 5)))) == []
