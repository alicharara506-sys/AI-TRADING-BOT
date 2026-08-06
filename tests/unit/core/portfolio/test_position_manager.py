from __future__ import annotations

import pytest

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.interfaces.events import OrderFilled, OrderSubmitted, PositionClosed
from core.interfaces.types import (
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
)
from core.portfolio.position_manager import PositionManager

_SYMBOL = Symbol(name="EURUSD")


def _request(correlation_id: str, side: OrderSide, volume: float) -> OrderRequest:
    return OrderRequest(
        correlation_id=correlation_id,
        symbol=_SYMBOL,
        side=side,
        order_type=OrderType.MARKET,
        volume=volume,
    )


async def _fill(
    event_bus: EventBus, correlation_id: str, side: OrderSide, volume: float, price: float
) -> None:
    await event_bus.publish(OrderSubmitted(request=_request(correlation_id, side, volume)))
    ack = OrderAck(
        correlation_id=correlation_id,
        broker_order_id=f"b-{correlation_id}",
        status=OrderStatus.FILLED,
        fill_price=price,
    )
    await event_bus.publish(OrderFilled(ack=ack))


def _setup() -> tuple[EventBus, PositionManager]:
    event_bus = EventBus()
    order_manager = OrderManager(event_bus)
    position_manager = PositionManager(order_manager, event_bus)
    return event_bus, position_manager


@pytest.mark.asyncio
async def test_first_fill_opens_position() -> None:
    event_bus, positions = _setup()

    await _fill(event_bus, "buy-1", OrderSide.BUY, 0.1, 1.1000)

    position = positions.get_position(_SYMBOL)
    assert position is not None
    assert position.side == OrderSide.BUY
    assert position.volume == pytest.approx(0.1)
    assert position.open_price == pytest.approx(1.1000)


@pytest.mark.asyncio
async def test_same_side_fill_averages_price_and_increases_volume() -> None:
    event_bus, positions = _setup()
    await _fill(event_bus, "buy-1", OrderSide.BUY, 0.1, 1.1000)
    await _fill(event_bus, "buy-2", OrderSide.BUY, 0.1, 1.1010)

    position = positions.get_position(_SYMBOL)
    assert position is not None
    assert position.volume == pytest.approx(0.2)
    assert position.open_price == pytest.approx(1.1005)


@pytest.mark.asyncio
async def test_opposite_side_partial_fill_reduces_volume_only() -> None:
    event_bus, positions = _setup()
    await _fill(event_bus, "buy-1", OrderSide.BUY, 0.3, 1.1000)
    await _fill(event_bus, "sell-1", OrderSide.SELL, 0.1, 1.1010)

    position = positions.get_position(_SYMBOL)
    assert position is not None
    assert position.side == OrderSide.BUY
    assert position.volume == pytest.approx(0.2)
    assert position.open_price == pytest.approx(1.1000)


@pytest.mark.asyncio
async def test_opposite_side_exact_fill_closes_position_and_publishes_event() -> None:
    event_bus, positions = _setup()
    closed: list[PositionClosed] = []
    event_bus.subscribe(PositionClosed, lambda e: closed.append(e))

    await _fill(event_bus, "buy-1", OrderSide.BUY, 0.1, 1.1000)
    await _fill(event_bus, "sell-1", OrderSide.SELL, 0.1, 1.1020)

    assert positions.get_position(_SYMBOL) is None
    assert len(closed) == 1
    assert closed[0].position.volume == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_opposite_side_larger_fill_closes_and_reverses() -> None:
    event_bus, positions = _setup()
    closed: list[PositionClosed] = []
    event_bus.subscribe(PositionClosed, lambda e: closed.append(e))

    await _fill(event_bus, "buy-1", OrderSide.BUY, 0.1, 1.1000)
    await _fill(event_bus, "sell-1", OrderSide.SELL, 0.3, 1.1020)

    assert len(closed) == 1
    position = positions.get_position(_SYMBOL)
    assert position is not None
    assert position.side == OrderSide.SELL
    assert position.volume == pytest.approx(0.2)
    assert position.open_price == pytest.approx(1.1020)


@pytest.mark.asyncio
async def test_fill_for_unknown_order_raises() -> None:
    event_bus = EventBus()
    order_manager = OrderManager(event_bus)
    PositionManager(order_manager, event_bus)

    ack = OrderAck(
        correlation_id="ghost", broker_order_id="1", status=OrderStatus.FILLED, fill_price=1.1
    )
    with pytest.raises(ExceptionGroup):
        await event_bus.publish(OrderFilled(ack=ack))


@pytest.mark.asyncio
async def test_list_positions_returns_all_open_positions() -> None:
    event_bus, positions = _setup()
    await _fill(event_bus, "buy-1", OrderSide.BUY, 0.1, 1.1000)

    assert len(positions.list_positions()) == 1
