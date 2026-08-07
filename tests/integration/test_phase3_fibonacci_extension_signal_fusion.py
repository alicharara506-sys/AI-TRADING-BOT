from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from quant.fibonacci.confluence import FibonacciConfluenceModule
from quant.fibonacci.extensions import FibonacciExtensionModule

_SYMBOL = Symbol(name="EURUSD")

# The same sharp-V-approach fixture verified in test_extensions.py: a deep
# low, a swing high whose immediate "double dip" pullback is disqualified
# from reconfirming a newer swing low (each dip bar has a lower neighbor
# within its own confirmation window), so price resuming its climb toward
# the 1.618 extension target is read against the original (low, high) leg.
_PRICES = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18,
    1.19, 1.22, 1.25, 1.30, 1.3236, 1.322,
]


def _context() -> MarketContext:
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=p,
            high=p,
            low=p,
            close=p,
            volume=1.0,
        )
        for i, p in enumerate(_PRICES)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


def test_fibonacci_extension_module_composes_through_unmodified_signal_fusion() -> None:
    """Phase 3's Fibonacci extension module registers into the exact same
    SignalEngine/SignalFusion every earlier phase's modules already use,
    with zero changes to core/signal/fusion.py. On this breakout-beyond-the-
    swing-high fixture, FibonacciConfluenceModule (a pullback/retracement
    read) correctly abstains -- price isn't retracing, it's extending --
    while FibonacciExtensionModule correctly fires, since the two modules
    are complementary reads of the same swing leg, not competitors.
    """
    engine = SignalEngine(SignalFusion(threshold=0.5))
    engine.register_module(FibonacciExtensionModule(swing_arm=2, tolerance=0.03))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))

    signal = engine.evaluate(_context())

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.combined_confidence > 0.5

    contributing = {item.source_module for item in signal.evidence}
    assert contributing == {"fibonacci_extension"}

    record = engine.history()[0]
    assert "fibonacci_extension" in record.explain()
