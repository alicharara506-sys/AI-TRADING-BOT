from __future__ import annotations

from datetime import datetime

from core.interfaces.types import (
    AccountState,
    OrderAck,
    OrderRequest,
    OrderStatus,
    Position,
    Symbol,
    SymbolInfo,
    Timeframe,
    Trade,
)


class FakeConnector:
    """Shared Connector Protocol test double: fills every market order at a
    configurable fixed price. Stands in for a real MT4/MT5 adapter wherever a test
    only needs "some connector", not real venue behavior."""

    def __init__(self, *, fill_price: float = 1.1000) -> None:
        self._connected = False
        self.fill_price = fill_price
        self.submitted_requests: list[OrderRequest] = []

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def subscribe_ticks(self, symbol: Symbol) -> None:
        return None

    async def subscribe_bars(self, symbol: Symbol, timeframe: Timeframe) -> None:
        return None

    async def get_symbol_info(self, symbol: Symbol) -> SymbolInfo:
        raise NotImplementedError("FakeConnector does not model symbol metadata")

    async def get_trade_history(self, from_ts: datetime, to_ts: datetime) -> list[Trade]:
        return []

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        self.submitted_requests.append(request)
        return OrderAck(
            correlation_id=request.correlation_id,
            broker_order_id=f"fake-{len(self.submitted_requests)}",
            status=OrderStatus.FILLED,
            fill_price=self.fill_price,
        )

    async def modify_position(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None:
        return None

    async def close_position(self, position_id: str, *, volume: float | None = None) -> None:
        return None

    async def get_open_positions(self) -> list[Position]:
        return []

    async def get_account_state(self) -> AccountState:
        return AccountState(
            balance=10_000.0,
            equity=10_000.0,
            margin=0.0,
            free_margin=10_000.0,
            margin_level=None,
            currency="USD",
        )


__all__ = ["FakeConnector"]
