from __future__ import annotations

from dataclasses import dataclass

from core.interfaces.types import (
    AccountState,
    Bar,
    ConnectionState,
    OrderAck,
    OrderRequest,
    Position,
    Tick,
)


@dataclass(frozen=True, slots=True)
class TickReceived:
    tick: Tick


@dataclass(frozen=True, slots=True)
class BarClosed:
    bar: Bar


@dataclass(frozen=True, slots=True)
class OrderSubmitted:
    request: OrderRequest


@dataclass(frozen=True, slots=True)
class OrderFilled:
    ack: OrderAck
    fill_price: float


@dataclass(frozen=True, slots=True)
class OrderRejected:
    ack: OrderAck


@dataclass(frozen=True, slots=True)
class PositionModified:
    position: Position


@dataclass(frozen=True, slots=True)
class PositionClosed:
    position: Position


@dataclass(frozen=True, slots=True)
class AccountStateChanged:
    account_state: AccountState


@dataclass(frozen=True, slots=True)
class ConnectionStateChanged:
    state: ConnectionState


@dataclass(frozen=True, slots=True)
class PositionDiscrepancy:
    expected: Position | None
    actual: Position | None
