from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from machine_learning.features.extractor import FeatureExtractor
from machine_learning.models.calibrated_classifier import CalibratedClassifier
from machine_learning.models.ml_signal_module import MLPredictionModule

_SYMBOL = Symbol(name="EURUSD")
_FEATURE_NAMES = ["return_1", "sma_distance", "ema_distance", "rsi", "volatility"]


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


def _fitted_model(seed: int = 0) -> CalibratedClassifier:
    rng = np.random.default_rng(seed)
    features: list[dict[str, float]] = []
    labels: list[int] = []
    for _ in range(200):
        r = float(rng.normal(0, 0.01))
        features.append(
            {
                "return_1": r,
                "sma_distance": float(rng.normal(0, 0.01)),
                "ema_distance": float(rng.normal(0, 0.01)),
                "rsi": float(rng.uniform(30, 70)),
                "volatility": float(rng.uniform(0.001, 0.02)),
            }
        )
        labels.append(1 if r > 0 else 0)
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES, random_state=seed)
    model.fit(features, labels)
    return model


def test_rejects_invalid_neutral_band() -> None:
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES)
    extractor = FeatureExtractor()

    with pytest.raises(ValueError):
        MLPredictionModule(model, extractor, neutral_band=0.5)


def test_unfitted_model_abstains() -> None:
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES)
    extractor = FeatureExtractor(sma_period=5, ema_period=5, rsi_period=5)
    module = MLPredictionModule(model, extractor)

    closes = [1.00 + 0.01 * i for i in range(20)]
    assert module.analyze(_context(closes)) == []


def test_fitted_model_predicts_long_on_uptrend() -> None:
    extractor = FeatureExtractor(sma_period=5, ema_period=5, rsi_period=5)
    module = MLPredictionModule(_fitted_model(), extractor)

    closes = [1.00 + 0.01 * i for i in range(20)]
    evidence = module.analyze(_context(closes))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG
    assert evidence[0].confidence > 0.9
    assert evidence[0].source_module == "ml_prediction"


def test_fitted_model_predicts_short_on_downtrend() -> None:
    extractor = FeatureExtractor(sma_period=5, ema_period=5, rsi_period=5)
    module = MLPredictionModule(_fitted_model(), extractor)

    closes = [1.20 - 0.01 * i for i in range(20)]
    evidence = module.analyze(_context(closes))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].confidence > 0.9


def test_too_few_bars_abstains() -> None:
    extractor = FeatureExtractor(sma_period=10, ema_period=10, rsi_period=14)
    module = MLPredictionModule(_fitted_model(), extractor)

    assert module.analyze(_context([1.0, 1.01, 1.02])) == []
