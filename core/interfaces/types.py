from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class Timeframe(enum.Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


class AccountMode(enum.Enum):
    NETTING = "netting"
    HEDGING = "hedging"


class OrderSide(enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ConnectionState(enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    LOST = "lost"


class Direction(enum.Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class Symbol:
    name: str
    broker_suffix: str = ""

    @property
    def canonical(self) -> str:
        return self.name.upper()


@dataclass(frozen=True, slots=True)
class Tick:
    symbol: Symbol
    timestamp: datetime
    bid: float
    ask: float
    volume: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: Symbol
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class SymbolInfo:
    symbol: Symbol
    digits: int
    point: float
    contract_size: float
    min_volume: float
    max_volume: float
    volume_step: float
    account_mode: AccountMode


@dataclass(frozen=True, slots=True)
class OrderRequest:
    correlation_id: str
    symbol: Symbol
    side: OrderSide
    order_type: OrderType
    volume: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass(frozen=True, slots=True)
class OrderAck:
    correlation_id: str
    broker_order_id: str
    status: OrderStatus
    fill_price: float | None = None
    commission: float = 0.0
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Position:
    position_id: str
    symbol: Symbol
    side: OrderSide
    volume: float
    open_price: float
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass(frozen=True, slots=True)
class Trade:
    trade_id: str
    symbol: Symbol
    side: OrderSide
    volume: float
    open_price: float
    close_price: float
    open_time: datetime
    close_time: datetime
    profit: float


@dataclass(frozen=True, slots=True)
class AccountState:
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float | None
    currency: str


@dataclass(frozen=True, slots=True)
class Evidence:
    source_module: str
    direction: Direction
    confidence: float
    rationale: dict[str, Any] = field(default_factory=dict)
    supporting_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TradeSignal:
    symbol: Symbol
    direction: Direction
    combined_confidence: float
    threshold: float
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class MarketContext:
    symbol: Symbol
    bars: tuple[Bar, ...]
    ticks: tuple[Tick, ...] = ()
    # Optional bars for OTHER timeframes of the same symbol, keyed by
    # Timeframe -- populated by callers that fetch multi-timeframe data
    # (see live_trading/multi_timeframe.py), read by modules like
    # HigherTimeframeAlignmentModule (quant/multi_timeframe/alignment.py).
    # Defaults to empty so every existing AnalysisModule and every existing
    # caller that only ever knew about `bars` keeps working unchanged.
    higher_timeframe_bars: dict[Timeframe, tuple[Bar, ...]] = field(default_factory=dict)
