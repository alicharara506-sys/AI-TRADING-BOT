from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, MarketContext, Symbol, Timeframe
from machine_learning.features.extractor import FeatureExtractor

_SYMBOL = Symbol(name="EURUSD")


def _context(closes: list[float]) -> MarketContext:
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=0.0,
        )
        for i, close in enumerate(closes)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


def test_rejects_invalid_periods() -> None:
    with pytest.raises(ValueError):
        FeatureExtractor(sma_period=0)


def test_feature_names_matches_extracted_keys() -> None:
    extractor = FeatureExtractor(sma_period=5, ema_period=5, rsi_period=5)
    closes = [1.00 + 0.01 * i for i in range(20)]

    features = extractor.extract(_context(closes))

    assert features is not None
    assert set(features.keys()) == set(extractor.feature_names())


def test_extract_on_steady_uptrend_produces_sensible_values() -> None:
    # Verified empirically: this exact fixture yields rsi=100.0 (no losing
    # bars at all in a strictly monotonic rise) and a positive sma/ema
    # distance (price trading above both moving averages).
    extractor = FeatureExtractor(sma_period=5, ema_period=5, rsi_period=5)
    closes = [1.00 + 0.01 * i for i in range(20)]

    features = extractor.extract(_context(closes))

    assert features is not None
    assert features["rsi"] == pytest.approx(100.0)
    assert features["sma_distance"] > 0
    assert features["ema_distance"] > 0
    assert features["return_1"] > 0


def test_too_few_bars_returns_none() -> None:
    extractor = FeatureExtractor(sma_period=10, ema_period=10, rsi_period=14)

    assert extractor.extract(_context([1.0, 1.01, 1.02])) is None
