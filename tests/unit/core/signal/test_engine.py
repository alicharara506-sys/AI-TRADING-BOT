from __future__ import annotations

from datetime import UTC, datetime

from core.interfaces.types import (
    Bar,
    Direction,
    Evidence,
    MarketContext,
    Symbol,
    Timeframe,
)
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion

_SYMBOL = Symbol(name="EURUSD")


def _context() -> MarketContext:
    bar = Bar(
        symbol=_SYMBOL,
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=1.1,
        high=1.1,
        low=1.1,
        close=1.1,
    )
    return MarketContext(symbol=_SYMBOL, bars=(bar,))


class _FixedModule:
    def __init__(self, name: str, evidence: list[Evidence]) -> None:
        self.name = name
        self._evidence = evidence

    def analyze(self, context: MarketContext) -> list[Evidence]:
        return self._evidence


def test_evaluate_fuses_evidence_from_all_registered_modules() -> None:
    engine = SignalEngine(SignalFusion(threshold=0.5))
    engine.register_module(
        _FixedModule("a", [Evidence(source_module="a", direction=Direction.LONG, confidence=0.9)])
    )
    engine.register_module(
        _FixedModule("b", [Evidence(source_module="b", direction=Direction.LONG, confidence=0.6)])
    )

    signal = engine.evaluate(_context())

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert len(signal.evidence) == 2


def test_evaluate_persists_a_record_even_below_threshold() -> None:
    engine = SignalEngine(SignalFusion(threshold=0.95))
    engine.register_module(
        _FixedModule("a", [Evidence(source_module="a", direction=Direction.LONG, confidence=0.6)])
    )

    signal = engine.evaluate(_context())

    assert signal is None
    history = engine.history()
    assert len(history) == 1
    assert history[0].signal is None
    assert len(history[0].evidence) == 1


def test_record_explain_is_human_readable() -> None:
    engine = SignalEngine(SignalFusion(threshold=0.5))
    engine.register_module(
        _FixedModule("a", [Evidence(source_module="a", direction=Direction.LONG, confidence=0.9)])
    )

    engine.evaluate(_context())
    record = engine.history()[0]
    text = record.explain()

    assert "EURUSD" in text
    assert "a" in text
    assert "LONG" in text


def test_no_registered_modules_produces_empty_evidence_and_no_signal() -> None:
    engine = SignalEngine(SignalFusion(threshold=0.5))

    signal = engine.evaluate(_context())

    assert signal is None
    assert engine.history()[0].evidence == ()


def test_history_accumulates_across_multiple_evaluations() -> None:
    engine = SignalEngine(SignalFusion(threshold=0.5))
    engine.register_module(
        _FixedModule("a", [Evidence(source_module="a", direction=Direction.LONG, confidence=0.9)])
    )

    engine.evaluate(_context())
    engine.evaluate(_context())

    assert len(engine.history()) == 2
