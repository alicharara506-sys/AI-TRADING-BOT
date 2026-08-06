from __future__ import annotations

from datetime import UTC, datetime, timedelta

from analytics.hit_rate_store import HistoricalHitRateStore
from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.risk.sizing import FixedVolumeSizingModel
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from decision_engine.engine import DecisionEngine
from quant.candlesticks.patterns import EngulfingPatternModule
from quant.fibonacci.confluence import FibonacciConfluenceModule

_SYMBOL = Symbol(name="EURUSD")
# Same verified bullish Engulfing + 61.8% Fibonacci confluence fixture used
# by this platform's other Signal Fusion exit-criteria tests.
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


def test_full_pipeline_from_quant_modules_through_a_decision_report() -> None:
    """Phase 8 exit criteria: real quant AnalysisModules feed real Evidence
    into a SignalFusion that weights each module by its own historical
    reliability (Phase 13's HistoricalHitRateStore, wired in via the new
    ModuleReliabilityProvider Protocol), and the resulting TradeSignal
    flows into DecisionEngine to produce a full DecisionReport -- position
    size, ATR-based stop-loss/take-profit, and an honest uncertainty read
    -- with no individual module ever generating a trade independently.
    """
    hit_rate_store = HistoricalHitRateStore(min_samples=3)
    # Fibonacci confluence has a strong, real track record on this symbol;
    # give it enough history to be trusted at full-plus weight.
    for _ in range(8):
        hit_rate_store.record_outcome("fibonacci_confluence", "EURUSD", won=True)
    for _ in range(2):
        hit_rate_store.record_outcome("fibonacci_confluence", "EURUSD", won=False)

    engine = SignalEngine(SignalFusion(threshold=0.6, reliability_provider=hit_rate_store))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))
    engine.register_module(EngulfingPatternModule())

    context = _context()
    signal = engine.evaluate(context)

    assert signal is not None
    assert signal.direction == Direction.LONG
    contributing = {item.source_module for item in signal.evidence}
    assert contributing == {"fibonacci_confluence", "engulfing_pattern"}

    decision_engine = DecisionEngine(
        FixedVolumeSizingModel(0.2),
        reliability_store=hit_rate_store,
        atr_period=14,
        atr_multiple=2.0,
        risk_reward_ratio=1.5,
    )
    report = decision_engine.decide(signal, context, equity=25_000.0)

    assert report.signal is signal
    assert report.confidence == signal.combined_confidence
    assert report.probability_of_success == signal.combined_confidence
    assert report.recommended_position_size == 0.2

    entry_price = context.bars[-1].close
    assert report.recommended_stop_loss is not None
    assert report.recommended_take_profit is not None
    assert report.recommended_stop_loss < entry_price  # LONG: stop below entry
    assert report.recommended_take_profit > entry_price  # LONG: target above entry

    risk = entry_price - report.recommended_stop_loss
    reward = report.recommended_take_profit - entry_price
    assert reward / risk > 1.49  # matches the configured 1.5 risk/reward ratio

    # engulfing_pattern has zero recorded history -> weakest link -> "high"
    # uncertainty, even though fibonacci_confluence has a strong track record.
    assert report.uncertainty == "high"
