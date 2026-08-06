from __future__ import annotations

import pytest

from core.event_bus.bus import EventBus
from core.interfaces.events import OrderFilled, OrderRejected
from core.interfaces.types import (
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
)
from execution_backends.live.engine import LiveExecutionEngine
from tests.support.fake_connector import FakeConnector


def _market_order(correlation_id: str) -> OrderRequest:
    return OrderRequest(
        correlation_id=correlation_id,
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


@pytest.mark.asyncio
async def test_submit_order_filled_publishes_order_filled() -> None:
    event_bus = EventBus()
    connector = FakeConnector(fill_price=1.2345)
    engine = LiveExecutionEngine(connector, event_bus)

    filled: list[OrderFilled] = []
    event_bus.subscribe(OrderFilled, lambda e: filled.append(e))

    ack = await engine.submit_order(_market_order("buy-1"))

    assert ack.status == OrderStatus.FILLED
    assert ack.fill_price == pytest.approx(1.2345)
    assert len(filled) == 1
    assert filled[0].ack.correlation_id == "buy-1"
    assert connector.submitted_requests[0].correlation_id == "buy-1"


@pytest.mark.asyncio
async def test_submit_order_rejected_publishes_order_rejected() -> None:
    event_bus = EventBus()
    connector = FakeConnector()

    async def always_reject(request: OrderRequest) -> OrderAck:
        return OrderAck(
            correlation_id=request.correlation_id,
            broker_order_id="",
            status=OrderStatus.REJECTED,
            reason="no liquidity",
        )

    connector.submit_order = always_reject  # type: ignore[method-assign]
    engine = LiveExecutionEngine(connector, event_bus)

    rejected: list[OrderRejected] = []
    event_bus.subscribe(OrderRejected, lambda e: rejected.append(e))

    ack = await engine.submit_order(_market_order("buy-2"))

    assert ack.status == OrderStatus.REJECTED
    assert len(rejected) == 1
    assert rejected[0].ack.reason == "no liquidity"


@pytest.mark.asyncio
async def test_cancel_order_not_implemented() -> None:
    event_bus = EventBus()
    engine = LiveExecutionEngine(FakeConnector(), event_bus)

    with pytest.raises(NotImplementedError):
        await engine.cancel_order("buy-1")
