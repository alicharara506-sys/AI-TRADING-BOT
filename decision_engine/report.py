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
    SignalFusion, a SizingModel, and ATR already produce; it invents
    nothing. expected_return and market_regime are deliberately absent:
    honestly producing them needs a return-tracking feedback loop and real
    regime-classification research that don't exist yet (see
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


__all__ = ["DecisionReport"]
