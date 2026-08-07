from __future__ import annotations

from core.interfaces.types import Bar, MarketContext, TradeSignal
from core.signal.engine import SignalEngine


class SignalFusionStrategy:
    """Adapts a SignalEngine (any AnalysisModule roster, fused by
    SignalFusion) to the bar-by-bar Strategy Protocol live_trading drives.
    Buffers a rolling window of bars and re-evaluates the full roster fresh
    on every new bar -- the same "recompute from scratch, no hidden state"
    contract every AnalysisModule.analyze() already has. This class adds
    only the bar-buffering LiveRunner/SignalWatcher need; it invents no
    signal logic of its own, and the exact same SignalEngine/SignalFusion
    already proven by every quant-module integration test drives it.
    """

    def __init__(
        self,
        engine: SignalEngine,
        *,
        strategy_name: str = "signal_fusion",
        lookback: int = 300,
    ) -> None:
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        self.strategy_name = strategy_name
        self._engine = engine
        self._lookback = lookback
        self._bars: list[Bar] = []

    def on_bar(self, bar: Bar) -> TradeSignal | None:
        self._bars.append(bar)
        if len(self._bars) > self._lookback:
            del self._bars[: len(self._bars) - self._lookback]
        context = MarketContext(symbol=bar.symbol, bars=tuple(self._bars))
        return self._engine.evaluate(context)


__all__ = ["SignalFusionStrategy"]
