from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from core.interfaces.analysis import AnalysisModule
from core.interfaces.types import Bar, Evidence, MarketContext, TradeSignal
from core.signal.fusion import SignalFusion
from quant.technical_analysis.directional_regime import (
    DirectionalRegime,
    compute_directional_regime,
)
from quant.technical_analysis.regime import VolatilityRegime, compute_volatility_regime

# Confidence multipliers keyed by AnalysisModule.name, applied before
# fusion when the trend/momentum/breakout modules' signal type is the one
# the ATLAS reference tracker's regime overlay trusts most in a confirmed
# trend. Capped at 1.0 in _reweight below (Evidence.confidence is already a
# probability-like value in [0,1]; a multiplier can shrink it but never
# manufacture confidence past that ceiling).
TREND_WEIGHT_MULTIPLIERS: dict[str, float] = {
    "adx_trend": 1.25,
    "macd_crossover": 1.25,
    "atr_volatility_breakout": 1.25,
    "donchian_breakout": 1.25,
    "market_structure": 1.15,
}

# In a confirmed mean-reversion regime, the ADF-gated counter-trend module
# and the band modules (Bollinger/Keltner, which already vote on
# distance-from-mean) are boosted; every module's confidence -- boosted or
# not -- is capped well below 1.0, since a counter-trend call in a
# still-uncalibrated system deserves more caution than a trend-following one.
MEAN_REVERT_WEIGHT_MULTIPLIERS: dict[str, float] = {
    "adf_mean_reversion": 1.25,
    "bollinger_band": 1.15,
    "keltner_channel": 1.15,
}
MEAN_REVERT_MAX_CONFIDENCE = 0.75

# High realized volatility doesn't change which module to trust -- it
# changes how much to risk. This mirrors the ATLAS reference tracker's
# HIGH_VOL overlay (0.25% risk, 2.0 ATR stop) as a caller-facing adjustment
# on top of whatever RiskEngine/DecisionEngine already compute, not a
# reimplementation of either.
HIGH_VOL_RISK_MULTIPLIER = 0.5
HIGH_VOL_ATR_MULTIPLE = 2.0


@dataclass(frozen=True, slots=True)
class RiskAdjustment:
    """A multiplier on whatever base account-risk fraction a SizingModel
    would otherwise use, plus an optional override for DecisionEngine's own
    atr_multiple. Both default to "change nothing" (1.0 / None) outside a
    high-volatility regime."""

    risk_multiplier: float = 1.0
    atr_multiple: float | None = None


@dataclass(frozen=True, slots=True)
class RoutedSignal:
    signal: TradeSignal | None
    directional_regime: DirectionalRegime | None
    volatility_regime: VolatilityRegime | None
    risk_adjustment: RiskAdjustment


class RegimeAwareStrategyRouter:
    """Wraps the existing SignalEngine/SignalFusion pipeline with a
    regime-conditional weighting pass: every AnalysisModule in the roster
    still runs and still produces Evidence exactly as it always does, but
    each Evidence's confidence is rescaled by a per-regime multiplier
    table (see the module-level tables above) before SignalFusion ever
    sees it. Never generates evidence or a direction itself -- it only
    rescales what modules already produced, then hands the result to the
    same SignalFusion every other strategy in this platform already uses,
    stacking on top of (not replacing) SignalFusion's own
    reliability-based per-module weighting.

    directional_regime_fn/volatility_regime_fn default to the platform's
    real compute_directional_regime/compute_volatility_regime but are
    constructor-injectable, the same dependency-injection pattern used for
    SizingModel/ModuleReliabilityProvider elsewhere, so tests can supply a
    fixed regime without needing statistically-crafted bar data.
    """

    def __init__(
        self,
        modules: Sequence[AnalysisModule],
        fusion: SignalFusion,
        *,
        directional_regime_fn: Callable[
            [Sequence[Bar]], DirectionalRegime | None
        ] = compute_directional_regime,
        volatility_regime_fn: Callable[
            [Sequence[Bar]], VolatilityRegime | None
        ] = compute_volatility_regime,
    ) -> None:
        self._modules = list(modules)
        self._fusion = fusion
        self._directional_regime_fn = directional_regime_fn
        self._volatility_regime_fn = volatility_regime_fn

    def evaluate(self, context: MarketContext) -> RoutedSignal:
        directional_regime = self._directional_regime_fn(context.bars)
        volatility_regime = self._volatility_regime_fn(context.bars)

        evidence: list[Evidence] = []
        for module in self._modules:
            evidence.extend(
                self._reweight(item, directional_regime) for item in module.analyze(context)
            )

        signal = self._fusion.fuse(context.symbol, evidence)
        return RoutedSignal(
            signal=signal,
            directional_regime=directional_regime,
            volatility_regime=volatility_regime,
            risk_adjustment=self._risk_adjustment(volatility_regime),
        )

    def _reweight(self, evidence: Evidence, regime: DirectionalRegime | None) -> Evidence:
        multiplier, cap = self._multiplier_and_cap(regime, evidence.source_module)
        if multiplier == 1.0 and cap is None:
            return evidence
        confidence = min(evidence.confidence * multiplier, 1.0)
        if cap is not None:
            confidence = min(confidence, cap)
        return replace(evidence, confidence=confidence)

    def _multiplier_and_cap(
        self, regime: DirectionalRegime | None, module_name: str
    ) -> tuple[float, float | None]:
        if regime in ("trend_up", "trend_down"):
            return TREND_WEIGHT_MULTIPLIERS.get(module_name, 1.0), None
        if regime == "mean_revert":
            return MEAN_REVERT_WEIGHT_MULTIPLIERS.get(module_name, 1.0), MEAN_REVERT_MAX_CONFIDENCE
        return 1.0, None

    def _risk_adjustment(self, volatility_regime: VolatilityRegime | None) -> RiskAdjustment:
        if volatility_regime == "high":
            return RiskAdjustment(
                risk_multiplier=HIGH_VOL_RISK_MULTIPLIER, atr_multiple=HIGH_VOL_ATR_MULTIPLE
            )
        return RiskAdjustment()


__all__ = ["RegimeAwareStrategyRouter", "RiskAdjustment", "RoutedSignal"]
