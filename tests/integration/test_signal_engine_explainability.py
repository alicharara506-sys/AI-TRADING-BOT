from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from quant.candlesticks.patterns import EngulfingPatternModule
from quant.fibonacci.confluence import FibonacciConfluenceModule
from quant.statistics.mean_reversion import AdfMeanReversionModule

_SYMBOL = Symbol(name="EURUSD")

# Verified empirically: a swing low (1.00) -> swing high (1.20) impulse leg, then
# a pullback whose final two bars form a bullish Engulfing pattern closing
# exactly at the 61.8% Fibonacci retracement (1.0764) -- both modules fire LONG
# on the same bar, independently, and reinforce each other in fusion.
_CLOSES_UP_TO_SWING = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11,
    1.14, 1.17, 1.20, 1.18, 1.16, 1.14, 1.12, 1.10,
]


def _context() -> MarketContext:
    ohlc = [(c, c, c, c) for c in _CLOSES_UP_TO_SWING]
    ohlc.append((1.0715, 1.0715, 1.0705, 1.0705))  # tiny bearish candle
    ohlc.append((1.0700, 1.0764, 1.0700, 1.0764))  # bullish, engulfs it, closes at target
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=0.0,
        )
        for i, (o, h, low, c) in enumerate(ohlc)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


def test_trade_signal_persists_with_full_explainable_evidence_trail() -> None:
    """Phase 7's exit criteria: a TradeSignal persists with its full Evidence[]
    trail, queryable and human-readable -- proving the Evidence/fusion contract
    end to end with real (not stubbed) AnalysisModules.
    """
    engine = SignalEngine(SignalFusion(threshold=0.6))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))
    engine.register_module(EngulfingPatternModule())
    # Too little data for its window -- contributes nothing, and that's fine.
    engine.register_module(AdfMeanReversionModule(window=30))

    signal = engine.evaluate(_context())

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.combined_confidence > 0.6

    contributing_modules = {item.source_module for item in signal.evidence}
    assert contributing_modules == {"fibonacci_confluence", "engulfing_pattern"}

    # Queryable: the same result is retrievable from the engine's history, not
    # just the immediate return value.
    history = engine.history()
    assert len(history) == 1
    record = history[0]
    assert record.signal is signal
    assert record.evidence == signal.evidence

    # Human-readable: every contributing module and the final decision render as
    # plain text, with nothing missing from the record.
    explanation = record.explain()
    assert "EURUSD" in explanation
    assert "fibonacci_confluence" in explanation
    assert "engulfing_pattern" in explanation
    assert "LONG" in explanation
