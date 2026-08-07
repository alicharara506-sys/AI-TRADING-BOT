from __future__ import annotations

from collections.abc import Sequence

from core.interfaces.risk import SizingModel
from core.interfaces.types import Bar, Direction, MarketContext, TradeSignal
from decision_engine.reliability import HistoricalReliabilityStore
from decision_engine.report import DecisionReport
from quant.price_action.structure import compute_structure_invalidation_level
from quant.technical_analysis.momentum import compute_adx
from quant.technical_analysis.regime import compute_volatility_regime
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
        risk_reward_ratio_2: float = 3.0,
        adx_period: int = 14,
        trend_threshold: float = 25.0,
        volatility_lookback: int = 100,
        structure_swing_arm: int = 2,
        low_uncertainty_samples: int = _DEFAULT_LOW_UNCERTAINTY_SAMPLES,
        medium_uncertainty_samples: int = _DEFAULT_MEDIUM_UNCERTAINTY_SAMPLES,
    ) -> None:
        if atr_period < 2:
            raise ValueError("atr_period must be >= 2")
        if atr_multiple <= 0:
            raise ValueError("atr_multiple must be > 0")
        if risk_reward_ratio <= 0:
            raise ValueError("risk_reward_ratio must be > 0")
        if risk_reward_ratio_2 <= 0:
            raise ValueError("risk_reward_ratio_2 must be > 0")
        if adx_period < 2:
            raise ValueError("adx_period must be >= 2")
        if not 0.0 < trend_threshold < 100.0:
            raise ValueError("trend_threshold must be in (0.0, 100.0)")
        if volatility_lookback < 2:
            raise ValueError("volatility_lookback must be >= 2")
        if structure_swing_arm < 1:
            raise ValueError("structure_swing_arm must be >= 1")
        if medium_uncertainty_samples >= low_uncertainty_samples:
            raise ValueError("low_uncertainty_samples must exceed medium_uncertainty_samples")
        self._sizing_model = sizing_model
        self._reliability_store = reliability_store
        self._atr_period = atr_period
        self._atr_multiple = atr_multiple
        self._risk_reward_ratio = risk_reward_ratio
        self._risk_reward_ratio_2 = risk_reward_ratio_2
        self._adx_period = adx_period
        self._trend_threshold = trend_threshold
        self._volatility_lookback = volatility_lookback
        self._structure_swing_arm = structure_swing_arm
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
        stop_loss, take_profit = self._levels(signal, context, atr, self._risk_reward_ratio)
        _stop_loss_2, take_profit_2 = self._levels(
            signal, context, atr, self._risk_reward_ratio_2
        )
        risk_reward_ratio = (
            self._risk_reward_ratio if stop_loss is not None and take_profit is not None else None
        )
        stop_distance = (
            abs(context.bars[-1].close - stop_loss)
            if stop_loss is not None and context.bars
            else None
        )

        return DecisionReport(
            signal=signal,
            confidence=signal.combined_confidence,
            probability_of_success=signal.combined_confidence,
            recommended_position_size=self._sizing_model.size(
                signal, equity=equity, stop_distance=stop_distance
            ),
            recommended_stop_loss=stop_loss,
            recommended_take_profit=take_profit,
            uncertainty=self._uncertainty(signal),
            atr=atr,
            take_profit_2=take_profit_2,
            risk_reward_ratio=risk_reward_ratio,
            trend_tag=self._trend_tag(context.bars),
            volatility_tag=compute_volatility_regime(
                context.bars, atr_period=self._atr_period, lookback=self._volatility_lookback
            ),
            invalidation_level=compute_structure_invalidation_level(
                context.bars, signal.direction, swing_arm=self._structure_swing_arm
            ),
        )

    def _levels(
        self,
        signal: TradeSignal,
        context: MarketContext,
        atr: float | None,
        risk_reward_ratio: float,
    ) -> tuple[float | None, float | None]:
        if atr is None or not context.bars:
            return None, None

        entry_price = context.bars[-1].close
        stop_distance = atr * self._atr_multiple
        take_profit_distance = stop_distance * risk_reward_ratio

        if signal.direction is Direction.LONG:
            return entry_price - stop_distance, entry_price + take_profit_distance
        return entry_price + stop_distance, entry_price - take_profit_distance

    def _trend_tag(self, bars: Sequence[Bar]) -> str | None:
        result = compute_adx(bars, period=self._adx_period)
        if result is None:
            return None
        plus_di, minus_di, adx = result
        if adx < self._trend_threshold:
            return "ranging"
        if plus_di > minus_di:
            return "uptrend"
        if minus_di > plus_di:
            return "downtrend"
        return "ranging"

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
