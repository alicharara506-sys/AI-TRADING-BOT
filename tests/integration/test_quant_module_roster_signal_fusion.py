from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from quant.candlesticks.patterns import EngulfingPatternModule
from quant.fibonacci.confluence import FibonacciConfluenceModule
from quant.price_action.structure import MarketStructureModule
from quant.statistics.mean_reversion import AdfMeanReversionModule
from quant.technical_analysis.volatility import AtrVolatilityBreakoutModule
from quant.technical_analysis.volume import OnBalanceVolumeModule

_SYMBOL = Symbol(name="EURUSD")

# Reuses the exact fixture verified in Phase 7's own exit-criteria test: a
# bullish Engulfing pattern closing exactly at the 61.8% Fibonacci retracement.
_CLOSES_UP_TO_SWING = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11,
    1.14, 1.17, 1.20, 1.18, 1.16, 1.14, 1.12, 1.10,
]


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


def test_full_quant_module_roster_composes_through_unmodified_signal_fusion() -> None:
    """Phase 11's exit criteria: the full module roster built across Phases 7
    and 11 -- statistics, Fibonacci, candlesticks, price-action structure, and
    both new Technical Analysis Laboratory categories (volume, volatility) --
    registers into SignalEngine and fuses through SignalFusion with zero
    changes needed to core/signal/fusion.py.
    """
    engine = SignalEngine(SignalFusion(threshold=0.6))
    engine.register_module(AdfMeanReversionModule(window=30))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))
    engine.register_module(EngulfingPatternModule())
    engine.register_module(MarketStructureModule(swing_arm=2))
    engine.register_module(OnBalanceVolumeModule(lookback=10))
    engine.register_module(AtrVolatilityBreakoutModule(period=14))

    signal = engine.evaluate(_context())

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.combined_confidence > 0.6

    # Three of the six modules have evidence to contribute on this fixture --
    # including a conflicting OBV vote that the stronger LONG evidence still
    # correctly overrides. The other three correctly abstain (too little data
    # for the ADF/ATR windows, no qualifying structure break) rather than
    # erroring or fabricating a signal.
    contributing = {item.source_module for item in signal.evidence}
    assert contributing == {"fibonacci_confluence", "engulfing_pattern", "on_balance_volume"}

    record = engine.history()[0]
    assert record.signal is signal
    explanation = record.explain()
    assert "fibonacci_confluence" in explanation
    assert "engulfing_pattern" in explanation
    assert "on_balance_volume" in explanation
