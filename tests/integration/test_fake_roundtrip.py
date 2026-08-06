from __future__ import annotations

from datetime import datetime

import pytest

from core.event_bus.bus import EventBus
from core.interfaces.connector import Connector
from core.interfaces.events import OrderFilled, OrderSubmitted
from core.interfaces.execution import ExecutionEngine
from core.interfaces.types import (
    AccountMode,
    AccountState,
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Symbol,
    SymbolInfo,
    Timeframe,
    Trade,
)
from core.kernel.lifecycle import Kernel


class FakeConnector:
    """Stands in for a real MT4/MT5 adapter: same Connector contract, no real venue."""

    def __init__(self) -> None:
        self._connected = False

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
        return SymbolInfo(
            symbol=symbol,
            digits=5,
            point=0.00001,
            contract_size=100_000,
            min_volume=0.01,
            max_volume=100.0,
            volume_step=0.01,
            account_mode=AccountMode.HEDGING,
        )

    async def get_trade_history(self, from_ts: datetime, to_ts: datetime) -> list[Trade]:
        return []

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        return OrderAck(
            correlation_id=request.correlation_id,
            broker_order_id="fake-1",
            status=OrderStatus.FILLED,
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


class FakeExecutionEngine:
    """Real ExecutionEngine shape: publishes OrderSubmitted, calls the Connector,
    publishes OrderFilled. A live implementation differs only in which Connector it holds."""

    def __init__(self, connector: Connector, event_bus: EventBus) -> None:
        self._connector = connector
        self._event_bus = event_bus

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        await self._event_bus.publish(OrderSubmitted(request=request))
        ack = await self._connector.submit_order(request)
        await self._event_bus.publish(OrderFilled(ack=ack, fill_price=1.1000))
        return ack

    async def cancel_order(self, correlation_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_fake_connector_and_execution_engine_roundtrip_through_container() -> None:
    kernel = Kernel()
    container = kernel.container

    connector = FakeConnector()
    container.register_instance(Connector, connector)
    container.register_factory(
        ExecutionEngine,
        lambda: FakeExecutionEngine(container.resolve(Connector), kernel.event_bus),
    )

    received: list[OrderFilled] = []

    async def on_filled(event: OrderFilled) -> None:
        received.append(event)

    kernel.event_bus.subscribe(OrderFilled, on_filled)

    execution_engine = container.resolve(ExecutionEngine)
    request = OrderRequest(
        correlation_id="corr-1",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )

    ack = await execution_engine.submit_order(request)

    assert ack.status == OrderStatus.FILLED
    assert len(received) == 1
    assert received[0].ack.correlation_id == "corr-1"
