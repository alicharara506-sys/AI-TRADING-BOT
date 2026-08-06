from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from backtesting.validation.look_ahead import LookAheadBiasCheck
from backtesting.validation.monte_carlo import MonteCarloCheck
from backtesting.validation.pipeline import ValidationPipeline
from backtesting.validation.walk_forward import WalkForwardCheck
from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from machine_learning.ai_assistant.rule_based_reviewer import RuleBasedReviewer
from machine_learning.features.extractor import FeatureExtractor
from machine_learning.models.calibrated_classifier import CalibratedClassifier
from machine_learning.models.ml_signal_module import MLPredictionModule
from quant.candlesticks.patterns import EngulfingPatternModule
from quant.fibonacci.confluence import FibonacciConfluenceModule

_SYMBOL = Symbol(name="EURUSD")
_FEATURE_NAMES = ["return_1", "sma_distance", "ema_distance", "rsi", "volatility"]

# Reuses the same verified fixture as Phase 7/11's exit-criteria tests: a
# bullish Engulfing pattern closing exactly at the 61.8% Fibonacci retracement.
_CLOSES_UP_TO_SWING = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11,
    1.14, 1.17, 1.20, 1.18, 1.16, 1.14, 1.12, 1.10,
]


def _train_model() -> CalibratedClassifier:
    rng = np.random.default_rng(0)
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
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES, random_state=0)
    model.fit(features, labels)
    return model


def _context() -> MarketContext:
    ohlc = [(c, c, c, c) for c in _CLOSES_UP_TO_SWING]
    ohlc.append((1.0715, 1.0715, 1.0705, 1.0705))
    ohlc.append((1.0700, 1.0764, 1.0700, 1.0764))
    bars = tuple(
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
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


def test_trained_model_plugs_into_signal_fusion_and_reviewer_explains_it() -> None:
    """Phase 12's exit criteria, in two parts: (1) a trained calibrated
    classifier composes through the existing SignalEngine/SignalFusion
    alongside quant modules with zero changes to either, and (2) the
    rule-based AIReviewer explains the resulting TradeSignal in natural
    language grounded in that same Evidence.
    """
    model = _train_model()
    engine = SignalEngine(SignalFusion(threshold=0.6))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))
    engine.register_module(EngulfingPatternModule())
    engine.register_module(
        MLPredictionModule(model, FeatureExtractor(sma_period=5, ema_period=5, rsi_period=5))
    )

    signal = engine.evaluate(_context())

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.combined_confidence > 0.6
    contributing = {item.source_module for item in signal.evidence}
    assert contributing == {"fibonacci_confluence", "engulfing_pattern", "ml_prediction"}

    explanation = RuleBasedReviewer().explain_trade_signal(signal)
    assert "ml_prediction" in explanation
    assert "fibonacci_confluence" in explanation
    assert "LONG" in explanation


def test_reviewer_explains_a_real_validation_pipeline_report() -> None:
    """The same AIReviewer also grounds its review in a genuine Phase 8
    ValidationReport, not a synthetic stand-in.
    """
    robust_returns = [10, -4, 8, -3, 9, -5, 7, -2, 10, -4, 9, -5, 8, -3, 7, -4, 10, -2, 9, -3]
    timestamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(20)]
    pipeline = ValidationPipeline(
        walk_forward=WalkForwardCheck(max_degradation=0.5),
        monte_carlo=MonteCarloCheck(max_drawdown=30.0, iterations=500, seed=1),
        look_ahead=LookAheadBiasCheck(),
    )

    report = pipeline.run(
        strategy_name="steady_strategy", trade_returns=robust_returns, bar_timestamps=timestamps
    )
    assert report.passed

    review = RuleBasedReviewer().review_validation_report(report)

    assert "PASSED" in review
    assert "walk_forward" in review
    assert "monte_carlo_drawdown" in review
    assert "look_ahead_bias" in review
