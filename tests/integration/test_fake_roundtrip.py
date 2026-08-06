from __future__ import annotations

import pytest

from core.interfaces.connector import Connector
from core.interfaces.events import OrderFilled
from core.interfaces.execution import ExecutionEngine
from core.interfaces.types import OrderRequest, OrderSide, OrderStatus, OrderType, Symbol
from core.kernel.lifecycle import Kernel
from execution_backends.live.engine import LiveExecutionEngine
from tests.support.fake_connector import FakeConnector


@pytest.mark.asyncio
async def test_fake_connector_and_execution_engine_roundtrip_through_container() -> None:
    """Phase 1's exit criteria: a Connector and an ExecutionEngine, wired purely
    through the DI container, round-trip an order over the real Event Bus. Now that
    Phase 4 has a real LiveExecutionEngine, this test exercises it directly instead
    of a hand-rolled stand-in.
    """
    kernel = Kernel()
    container = kernel.container

    connector = FakeConnector()
    container.register_instance(Connector, connector)
    container.register_factory(
        ExecutionEngine,
        lambda: LiveExecutionEngine(container.resolve(Connector), kernel.event_bus),
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
