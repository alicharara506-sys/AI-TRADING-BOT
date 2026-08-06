from __future__ import annotations

from core.interfaces.risk import SizingModel
from core.interfaces.types import Direction, MarketContext, TradeSignal
from decision_engine.reliability import HistoricalReliabilityStore
from decision_engine.report import DecisionReport
from quant.technical_analysis.volatility import compute_atr

_DEFAULT_LOW_UNCERTAINTY_SAMPLES = 30
_DEFAULT_MEDIUM_UNCERTAINTY_SAMPLES = 10


class DecisionEngine:
    """Turns a TradeSignal (already produced by SignalFusion) into a
    decision-ready DecisionReport: position size from an injected
    SizingModel, ATR-based stop-loss/take-profit, and an uncertainty read
    from however much historical data backs the signal's contributing
    modules. Never generates a signal or a direction itself -- it strictly
    consumes what SignalFusion already decided, exactly preserving the
    "no individual module generates trades independently" rule the signal
    already satisfies by construction.
    """

    def __init__(
        self,
        sizing_model: SizingModel,
        *,
        reliability_store: HistoricalReliabilityStore | None = None,
        atr_period: int = 14,
        atr_multiple: float = 2.0,
        risk_reward_ratio: float = 1.5,
        low_uncertainty_samples: int = _DEFAULT_LOW_UNCERTAINTY_SAMPLES,
        medium_uncertainty_samples: int = _DEFAULT_MEDIUM_UNCERTAINTY_SAMPLES,
    ) -> None:
        if atr_period < 2:
            raise ValueError("atr_period must be >= 2")
        if atr_multiple <= 0:
            raise ValueError("atr_multiple must be > 0")
        if risk_reward_ratio <= 0:
            raise ValueError("risk_reward_ratio must be > 0")
        if medium_uncertainty_samples >= low_uncertainty_samples:
            raise ValueError("low_uncertainty_samples must exceed medium_uncertainty_samples")
        self._sizing_model = sizing_model
        self._reliability_store = reliability_store
        self._atr_period = atr_period
        self._atr_multiple = atr_multiple
        self._risk_reward_ratio = risk_reward_ratio
        self._low_uncertainty_samples = low_uncertainty_samples
        self._medium_uncertainty_samples = medium_uncertainty_samples

    def decide(
        self, signal: TradeSignal, context: MarketContext, *, equity: float
    ) -> DecisionReport:
        if signal.symbol != context.symbol:
            raise ValueError(
                f"signal is for '{signal.symbol.canonical}' but context is for "
                f"'{context.symbol.canonical}'"
            )

        atr = compute_atr(context.bars, period=self._atr_period)
        stop_loss, take_profit = self._levels(signal, context, atr)

        return DecisionReport(
            signal=signal,
            confidence=signal.combined_confidence,
            probability_of_success=signal.combined_confidence,
            recommended_position_size=self._sizing_model.size(signal, equity=equity),
            recommended_stop_loss=stop_loss,
            recommended_take_profit=take_profit,
            uncertainty=self._uncertainty(signal),
            atr=atr,
        )

    def _levels(
        self, signal: TradeSignal, context: MarketContext, atr: float | None
    ) -> tuple[float | None, float | None]:
        if atr is None or not context.bars:
            return None, None

        entry_price = context.bars[-1].close
        stop_distance = atr * self._atr_multiple
        take_profit_distance = stop_distance * self._risk_reward_ratio

        if signal.direction is Direction.LONG:
            return entry_price - stop_distance, entry_price + take_profit_distance
        return entry_price + stop_distance, entry_price - take_profit_distance

    def _uncertainty(self, signal: TradeSignal) -> str:
        if self._reliability_store is None:
            return "high"

        symbol = signal.symbol.canonical
        modules = {item.source_module for item in signal.evidence}
        sample_counts = [self._reliability_store.sample_count(module, symbol) for module in modules]
        weakest = min(sample_counts) if sample_counts else 0

        if weakest >= self._low_uncertainty_samples:
            return "low"
        if weakest >= self._medium_uncertainty_samples:
            return "medium"
        return "high"


__all__ = ["DecisionEngine"]
