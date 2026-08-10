from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.interfaces.types import Direction
from live_tracking.types import HitTarget

# Frozen, minimal event payloads -- deliberately not the mutable SignalOutcome
# itself (see live_tracking/types.py's docstring): a subscriber gets exactly
# the fields relevant to the event, the same design already used for
# OrderFilled/PositionClosed in core/interfaces/events.py.


@dataclass(frozen=True, slots=True)
class SignalOutcomeOpened:
    outcome_id: str
    symbol: str
    direction: Direction
    at: datetime


@dataclass(frozen=True, slots=True)
class SignalTriggered:
    outcome_id: str
    symbol: str
    trigger_price: float
    at: datetime


@dataclass(frozen=True, slots=True)
class TakeProfitHit:
    outcome_id: str
    symbol: str
    target: HitTarget
    price: float
    pips: float
    at: datetime


@dataclass(frozen=True, slots=True)
class StopLossHit:
    outcome_id: str
    symbol: str
    price: float
    pips: float
    at: datetime


@dataclass(frozen=True, slots=True)
class SignalExpired:
    outcome_id: str
    symbol: str
    at: datetime


__all__ = [
    "SignalExpired",
    "SignalOutcomeOpened",
    "SignalTriggered",
    "StopLossHit",
    "TakeProfitHit",
]
