from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from core.interfaces.types import (
    AccountState,
    OrderAck,
    OrderRequest,
    Position,
    Symbol,
    SymbolInfo,
    Timeframe,
    Trade,
)


@runtime_checkable
class Connector(Protocol):
    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    def is_connected(self) -> bool: ...

    async def subscribe_ticks(self, symbol: Symbol) -> None: ...

    async def subscribe_bars(self, symbol: Symbol, timeframe: Timeframe) -> None: ...

    async def get_symbol_info(self, symbol: Symbol) -> SymbolInfo: ...

    async def get_trade_history(self, from_ts: datetime, to_ts: datetime) -> list[Trade]: ...

    async def submit_order(self, request: OrderRequest) -> OrderAck: ...

    async def modify_position(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None: ...

    async def close_position(self, position_id: str, *, volume: float | None = None) -> None: ...

    async def get_open_positions(self) -> list[Position]: ...

    async def get_account_state(self) -> AccountState: ...
