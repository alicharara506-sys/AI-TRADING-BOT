from __future__ import annotations

import pytest

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.interfaces.events import OrderFilled, OrderRejected, OrderSubmitted
from core.interfaces.types import (
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
)


def _request(correlation_id: str = "corr-1") -> OrderRequest:
    return OrderRequest(
        correlation_id=correlation_id,
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


@pytest.mark.asyncio
async def test_submitted_then_filled_updates_order_state() -> None:
    event_bus = EventBus()
    manager = OrderManager(event_bus)
    request = _request()

    await event_bus.publish(OrderSubmitted(request=request))
    order = manager.get_order("corr-1")
    assert order is not None
    assert order.status == OrderStatus.SUBMITTED

    ack = OrderAck(
        correlation_id="corr-1",
        broker_order_id="99",
        status=OrderStatus.FILLED,
        fill_price=1.1,
    )
    await event_bus.publish(OrderFilled(ack=ack))

    order = manager.get_order("corr-1")
    assert order is not None
    assert order.status == OrderStatus.FILLED
    assert order.broker_order_id == "99"
    assert order.fill_price == pytest.approx(1.1)


@pytest.mark.asyncio
async def test_submitted_then_rejected_updates_order_state() -> None:
    event_bus = EventBus()
    manager = OrderManager(event_bus)
    request = _request("corr-2")

    await event_bus.publish(OrderSubmitted(request=request))
    ack = OrderAck(
        correlation_id="corr-2",
        broker_order_id="",
        status=OrderStatus.REJECTED,
        reason="no liquidity",
    )
    await event_bus.publish(OrderRejected(ack=ack))

    order = manager.get_order("corr-2")
    assert order is not None
    assert order.status == OrderStatus.REJECTED
    assert order.reason == "no liquidity"


@pytest.mark.asyncio
async def test_filled_event_for_unknown_order_raises() -> None:
    event_bus = EventBus()
    OrderManager(event_bus)
    ack = OrderAck(correlation_id="ghost", broker_order_id="1", status=OrderStatus.FILLED)

    with pytest.raises(ExceptionGroup):
        await event_bus.publish(OrderFilled(ack=ack))


@pytest.mark.asyncio
async def test_list_orders_returns_all_tracked_orders() -> None:
    event_bus = EventBus()
    manager = OrderManager(event_bus)

    await event_bus.publish(OrderSubmitted(request=_request("corr-a")))
    await event_bus.publish(OrderSubmitted(request=_request("corr-b")))

    ids = {order.request.correlation_id for order in manager.list_orders()}
    assert ids == {"corr-a", "corr-b"}
