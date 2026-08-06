from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from machine_learning.ai_assistant.llm_backed_reviewer import LLMBackedReviewer
from machine_learning.ai_assistant.rule_based_reviewer import RuleBasedReviewer
from quant.candlesticks.patterns import EngulfingPatternModule
from quant.fibonacci.confluence import FibonacciConfluenceModule
from tests.support.fake_llm_provider import FakeLLMProvider

_SYMBOL = Symbol(name="EURUSD")
# The same verified bullish Engulfing + 61.8% Fibonacci confluence fixture
# used by this phase's own exit-criteria tests since Phase 7/11/12.
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


async def test_llm_backed_reviewer_explains_a_real_signal_end_to_end() -> None:
    """Phase 4 (AI Intelligence Layer) exit criteria, part 1: a real
    TradeSignal produced by the unmodified Signal Fusion pipeline is
    explained by LLMBackedReviewer via a fake but structurally real
    LLMProvider, grounded in RuleBasedReviewer's own analysis of that exact
    signal, and rendered with the LLM's confidence and supporting points.
    """
    engine = SignalEngine(SignalFusion(threshold=0.6))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))
    engine.register_module(EngulfingPatternModule())

    signal = engine.evaluate(_context())
    assert signal is not None
    assert signal.direction == Direction.LONG

    provider = FakeLLMProvider(
        next_response=(
            '{"opinion": "A confluent long setup with agreement across two '
            'independent modules.", "confidence": 0.88, '
            '"supporting_points": ["fibonacci confluence", "engulfing pattern"]}'
        )
    )
    reviewer = LLMBackedReviewer(provider)

    explanation = await reviewer.explain_trade_signal(signal)

    assert "confluent long setup" in explanation
    assert "88%" in explanation
    assert "- fibonacci confluence" in explanation
    # The LLM was actually grounded in the real signal's own evidence, not
    # prompted blind.
    assert "fibonacci_confluence" in provider.prompts_received[0]
    assert "engulfing_pattern" in provider.prompts_received[0]
    assert "LONG" in provider.prompts_received[0]


async def test_llm_outage_falls_back_to_the_same_rule_based_explanation() -> None:
    """Phase 4 exit criteria, part 2: when the LLM provider is unavailable,
    the platform doesn't lose the ability to explain a signal -- it falls
    back to exactly what RuleBasedReviewer alone would have produced, byte
    for byte, and never propagates the provider's failure to the caller.
    """
    engine = SignalEngine(SignalFusion(threshold=0.6))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))
    engine.register_module(EngulfingPatternModule())
    signal = engine.evaluate(_context())
    assert signal is not None

    provider = FakeLLMProvider(error=ConnectionError("LLM provider unreachable"))
    reviewer = LLMBackedReviewer(provider)

    explanation = await reviewer.explain_trade_signal(signal)
    expected = await RuleBasedReviewer().explain_trade_signal(signal)

    assert explanation == expected
