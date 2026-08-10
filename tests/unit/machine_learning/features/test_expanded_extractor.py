from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, MarketContext, Symbol, Timeframe
from machine_learning.features.expanded_extractor import (
    ExpandedFeatureExtractor,
    compute_directional_efficiency,
    compute_rsi_zscore,
    compute_tick_volume_ratio,
    compute_vwap_deviation,
)

_SYMBOL = Symbol(name="EURUSD")


def _bars(
    closes: list[float], *, volumes: list[float] | None = None, highs: list[float] | None = None
) -> list[Bar]:
    volumes = volumes or [1.0] * len(closes)
    highs = highs or closes
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=close,
            high=highs[i],
            low=close,
            close=close,
            volume=volumes[i],
        )
        for i, close in enumerate(closes)
    ]


def _context(bars: list[Bar]) -> MarketContext:
    return MarketContext(symbol=_SYMBOL, bars=tuple(bars))


# ---- compute_rsi_zscore ----------------------------------------------------


def test_rsi_zscore_rejects_invalid_parameters() -> None:
    bars = _bars([1.0] * 60)
    with pytest.raises(ValueError):
        compute_rsi_zscore(bars, rsi_period=0)
    with pytest.raises(ValueError):
        compute_rsi_zscore(bars, zscore_window=1)


def test_rsi_zscore_is_none_without_a_full_window() -> None:
    bars = _bars([1.0 + 0.01 * i for i in range(20)])
    assert compute_rsi_zscore(bars, rsi_period=5, zscore_window=50) is None


def test_rsi_zscore_is_zero_for_a_perfectly_flat_rsi_history() -> None:
    # A strictly monotonic rise makes RSI saturate at 100.0 for every bar
    # once the seed window has passed -- constant RSI means zero variance,
    # so the z-score must be the documented 0.0 fallback, not a division
    # by a near-zero standard deviation.
    bars = _bars([1.0 + 0.01 * i for i in range(80)])
    assert compute_rsi_zscore(bars, rsi_period=5, zscore_window=50) == pytest.approx(0.0)


def test_rsi_zscore_is_positive_after_an_unusually_strong_rally() -> None:
    oscillating = [1.0 + 0.01 * (i % 2) for i in range(60)]
    rally = [oscillating[-1] + 0.01 * i for i in range(1, 10)]
    bars = _bars(oscillating + rally)

    zscore = compute_rsi_zscore(bars, rsi_period=5, zscore_window=50)

    assert zscore is not None
    assert zscore > 0


# ---- compute_directional_efficiency ----------------------------------------


def test_directional_efficiency_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        compute_directional_efficiency(_bars([1.0] * 20), period=0)


def test_directional_efficiency_is_none_with_insufficient_bars() -> None:
    assert compute_directional_efficiency(_bars([1.0, 1.01]), period=14) is None


def test_directional_efficiency_is_one_for_a_straight_line_move() -> None:
    closes = [1.0 + 0.01 * i for i in range(15)]
    assert compute_directional_efficiency(_bars(closes), period=14) == pytest.approx(1.0)


def test_directional_efficiency_is_low_for_pure_chop() -> None:
    closes = [1.0 + (0.01 if i % 2 == 0 else -0.01) for i in range(15)]
    efficiency = compute_directional_efficiency(_bars(closes), period=14)

    assert efficiency is not None
    assert efficiency < 0.2


# ---- compute_tick_volume_ratio ---------------------------------------------


def test_tick_volume_ratio_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        compute_tick_volume_ratio(_bars([1.0] * 20), period=0)


def test_tick_volume_ratio_is_none_with_insufficient_bars() -> None:
    assert compute_tick_volume_ratio(_bars([1.0, 1.01]), period=20) is None


def test_tick_volume_ratio_is_none_when_trailing_average_is_zero() -> None:
    closes = [1.0] * 6
    volumes = [0.0] * 6
    assert compute_tick_volume_ratio(_bars(closes, volumes=volumes), period=5) is None


def test_tick_volume_ratio_reflects_a_volume_spike() -> None:
    closes = [1.0] * 6
    volumes = [1.0, 1.0, 1.0, 1.0, 1.0, 5.0]
    ratio = compute_tick_volume_ratio(_bars(closes, volumes=volumes), period=5)

    assert ratio == pytest.approx(5.0)


# ---- compute_vwap_deviation -------------------------------------------------


def test_vwap_deviation_is_none_with_insufficient_bars() -> None:
    assert compute_vwap_deviation(_bars([1.0, 1.01], volumes=[1.0, 1.0])) is None


def test_vwap_deviation_is_positive_when_price_trades_above_vwap() -> None:
    closes = [1.0] * 19 + [1.5]
    volumes = [1.0] * 20
    highs = closes
    bars = _bars(closes, volumes=volumes, highs=highs)

    deviation = compute_vwap_deviation(bars, vwap_period=20, atr_period=14)

    assert deviation is not None
    assert deviation > 0


# ---- ExpandedFeatureExtractor -----------------------------------------------


def _rich_bars(count: int) -> list[Bar]:
    closes = [1.0 + 0.001 * (i % 7) + 0.0005 * i for i in range(count)]
    volumes = [1.0 + 0.1 * (i % 5) for i in range(count)]
    highs = [c + 0.002 for c in closes]
    return _bars(closes, volumes=volumes, highs=highs)


def test_extract_returns_none_without_enough_history() -> None:
    extractor = ExpandedFeatureExtractor()
    assert extractor.extract(_context(_rich_bars(30))) is None


def test_extract_returns_every_declared_feature_name() -> None:
    extractor = ExpandedFeatureExtractor()
    features = extractor.extract(_context(_rich_bars(140)))

    assert features is not None
    assert set(features.keys()) == set(extractor.feature_names())


def test_extract_normalizes_bounded_features_into_zero_one() -> None:
    extractor = ExpandedFeatureExtractor()
    features = extractor.extract(_context(_rich_bars(140)))

    assert features is not None
    assert 0.0 <= features["directional_efficiency"] <= 1.0
    assert 0.0 <= features["tick_volume_ratio"] <= 1.0
    assert 0.0 <= features["atr_percentile"] <= 1.0
