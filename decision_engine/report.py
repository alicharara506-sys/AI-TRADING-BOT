from __future__ import annotations

from dataclasses import dataclass

from core.interfaces.types import TradeSignal


@dataclass(frozen=True, slots=True)
class DecisionReport:
    """The unified, decision-ready view of a TradeSignal: what Signal
    Fusion already computed (confidence, direction, evidence), plus what
    sizing and volatility add on top (position size, stop-loss,
    take-profit), plus an honest read of how much historical data backs
    the modules that produced this signal (uncertainty).

    Every field traces to a real, already-verified computation elsewhere
    in the platform -- DecisionEngine orchestrates and surfaces what
    SignalFusion, a SizingModel, ATR, ADX, and the shared swing-detection
    primitive already produce; it invents nothing. trend_tag and
    volatility_tag are two separate, honestly-computed *factual* readings
    (ADX-confirmed trend direction; ATR-percentile-vs-own-history), not a
    single fabricated composite "regime" label -- that distinction matters
    (see quant/technical_analysis/regime.py's own docstring). expected_return
    is still deliberately absent: honestly producing it needs a
    return-tracking feedback loop that doesn't exist yet (see
    docs/architecture/09-decision-engine.md).
    """

    signal: TradeSignal
    confidence: float
    probability_of_success: float
    recommended_position_size: float
    recommended_stop_loss: float | None
    recommended_take_profit: float | None
    uncertainty: str
    atr: float | None
    # Second take-profit target, at a further (configurable) risk/reward
    # multiple than recommended_take_profit -- a common two-target exit plan.
    take_profit_2: float | None = None
    # The realized risk/reward ratio recommended_take_profit was built at
    # (echoes DecisionEngine's own configured ratio; None when no stop/target
    # exists to compute it from).
    risk_reward_ratio: float | None = None
    trend_tag: str | None = None
    volatility_tag: str | None = None
    # Where the trade's own structural premise breaks (nearest confirmed
    # swing low for a LONG, swing high for a SHORT) -- distinct from
    # recommended_stop_loss, which is sized off volatility (ATR) alone and
    # may sit inside or outside where market structure would actually call it.
    invalidation_level: float | None = None


__all__ = ["DecisionReport"]
