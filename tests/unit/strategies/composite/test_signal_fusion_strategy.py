from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, Evidence, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from strategies.composite.signal_fusion_strategy import SignalFusionStrategy

_SYMBOL = Symbol(name="EURUSD")


def _bar(price: float, i: int) -> Bar:
    return Bar(
        symbol=_SYMBOL,
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1.0,
    )


class _FiresOnceEnoughBarsModule:
    """A minimal fake AnalysisModule: fires a fixed-confidence LONG the
    moment the context accumulates `required_bars` bars, so tests can
    control exactly when SignalEngine.evaluate() produces a signal without
    depending on any real indicator's math.
    """

    name = "fake_module"

    def __init__(self, *, required_bars: int) -> None:
        self._required_bars = required_bars

    def analyze(self, context: MarketContext) -> list[Evidence]:
        if len(context.bars) < self._required_bars:
            return []
        return [Evidence(source_module=self.name, direction=Direction.LONG, confidence=0.9)]


def _engine(required_bars: int) -> SignalEngine:
    engine = SignalEngine(SignalFusion(threshold=0.6))
    engine.register_module(_FiresOnceEnoughBarsModule(required_bars=required_bars))
    return engine


def test_rejects_invalid_lookback() -> None:
    with pytest.raises(ValueError):
        SignalFusionStrategy(_engine(3), lookback=1)


def test_on_bar_returns_none_before_the_module_has_enough_bars() -> None:
    strategy = SignalFusionStrategy(_engine(required_bars=3), lookback=300)

    assert strategy.on_bar(_bar(1.10, 0)) is None
    assert strategy.on_bar(_bar(1.11, 1)) is None


def test_on_bar_returns_a_signal_once_the_module_fires() -> None:
    strategy = SignalFusionStrategy(_engine(required_bars=3), lookback=300)
    strategy.on_bar(_bar(1.10, 0))
    strategy.on_bar(_bar(1.11, 1))

    signal = strategy.on_bar(_bar(1.12, 2))

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.symbol == _SYMBOL


def test_strategy_name_defaults_and_is_overridable() -> None:
    default = SignalFusionStrategy(_engine(required_bars=1))
    assert default.strategy_name == "signal_fusion"

    named = SignalFusionStrategy(_engine(required_bars=1), strategy_name="my_roster")
    assert named.strategy_name == "my_roster"


def test_bars_buffer_is_trimmed_to_the_configured_lookback() -> None:
    # required_bars=3 but lookback=2: the buffer never holds 3 bars at once,
    # so the module can never see enough history to fire.
    strategy = SignalFusionStrategy(_engine(required_bars=3), lookback=2)

    for i in range(5):
        signal = strategy.on_bar(_bar(1.10 + i * 0.001, i))

    assert signal is None
