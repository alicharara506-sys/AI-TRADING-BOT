from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

from core.interfaces.types import Direction, SymbolInfo


class OutcomeStatus(enum.Enum):
    """Lifecycle state of a tracked signal. PENDING is a conditional
    (stop-order) signal waiting for its trigger_price to be touched;
    everything else already has a live position. TP1_HIT/TP2_HIT are
    deliberately *not* terminal: this platform never manages a trailing
    stop after a partial target, so a signal that reached TP1 keeps being
    tracked toward TP2/TP3/the original stop-loss exactly like the ATLAS
    reference tracker's own ladder (TP1 -> TP2 -> TP3, independently
    watching for SL the whole time). Only the final configured target
    (TP3_HIT, or TP2_HIT/TP1_HIT when no further target was set), SL_HIT,
    EXPIRED, and CLOSED_MANUAL (a user closing from the dashboard before
    any target/stop was reached) actually end tracking.
    """

    PENDING = "pending"
    ACTIVE = "active"
    TP1_HIT = "tp1_hit"
    TP2_HIT = "tp2_hit"
    TP3_HIT = "tp3_hit"
    SL_HIT = "sl_hit"
    EXPIRED = "expired"
    CLOSED_MANUAL = "closed_manual"


class HitTarget(enum.Enum):
    TP1 = "TP1"
    TP2 = "TP2"
    TP3 = "TP3"
    SL = "SL"


def pip_size_for(symbol_info: SymbolInfo) -> float:
    """Standard MT5 pip-size convention: a 3- or 5-digit quoted symbol (the
    common "fractional pip" broker convention for JPY pairs and most other
    instruments respectively) counts a pip as 10 points; a 2- or 4-digit
    quoted symbol counts a pip as 1 point. Used only to render human-scale
    "+197.3 pips" figures -- every stored price and every SL/TP comparison
    in this package uses raw price units, never pips, so a wrong guess here
    never affects trigger/hit detection, only the displayed pip count.
    """
    if symbol_info.digits in (3, 5):
        return symbol_info.point * 10.0
    return symbol_info.point


@dataclass(slots=True)
class LivePriceSample:
    price: float
    at: datetime


@dataclass(slots=True)
class SignalOutcome:
    """The live-tracked record of one DecisionReport, from generation to
    resolution. Unlike every other domain type in this platform (Tick, Bar,
    TradeSignal, ...), this is deliberately a *mutable* dataclass: it is a
    single stateful record that SignalLifecycleTracker updates in place on
    every relevant tick (status, highest/lowest pips, live price samples)
    for as long as it stays open, then persists via SignalRepository --
    it is bookkeeping state owned by the tracker, not an immutable value
    flowing through the EventBus (the events in live_tracking/events.py
    that *do* cross the EventBus stay frozen, carrying only the fields a
    subscriber needs, never this object itself).
    """

    id: str
    symbol: str
    direction: Direction
    strategy_name: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    pip_size: float
    timestamp_generated: datetime
    score_at_generation: float
    uncertainty_at_generation: str
    take_profit_2: float | None = None
    take_profit_3: float | None = None
    trigger_price: float | None = None
    regime_at_generation: str | None = None
    sentiment_at_generation: float | None = None
    ml_probability_at_generation: float | None = None
    status: OutcomeStatus = OutcomeStatus.ACTIVE
    live_price_samples: list[LivePriceSample] = field(default_factory=list)
    highest_pips: float = 0.0
    lowest_pips: float = 0.0
    final_pips: float | None = None
    achieved_risk_reward: float | None = None
    timestamp_triggered: datetime | None = None
    timestamp_resolved: datetime | None = None
    hit_target: HitTarget | None = None
    user_note: str | None = None
    user_reactions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.pip_size <= 0:
            raise ValueError("pip_size must be > 0")
        if self.trigger_price is not None:
            self.status = OutcomeStatus.PENDING

    @property
    def planned_risk_reward(self) -> float | None:
        """Planned R:R to TP1, the same first-target ratio DecisionReport's
        own risk_reward_ratio already represents -- recomputed here (rather
        than trusting a stale copy) from the stored entry/stop/TP1 so it
        always matches this outcome's own recorded levels.
        """
        risk = abs(self.entry_price - self.stop_loss)
        if risk <= 0:
            return None
        reward = abs(self.take_profit_1 - self.entry_price)
        return reward / risk

    def pips(self, price: float) -> float:
        """Signed pip distance of `price` from entry, positive when the
        move favors this outcome's direction."""
        distance = price - self.entry_price
        if self.direction is Direction.SHORT:
            distance = -distance
        return distance / self.pip_size


__all__ = [
    "HitTarget",
    "LivePriceSample",
    "OutcomeStatus",
    "SignalOutcome",
    "pip_size_for",
]
