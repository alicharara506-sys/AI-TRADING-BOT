from __future__ import annotations

import pytest

from core.event_bus.bus import EventBus
from core.interfaces.types import OrderRequest, OrderSide, OrderStatus, OrderType, Position, Symbol
from execution_backends.live.engine import LiveExecutionEngine
from live_trading.flip_safe_execution import FlipSafeExecutionEngine
from tests.support.fake_connector import FakeConnector

_SYMBOL = Symbol(name="EURUSD")


def _order(side: OrderSide, correlation_id: str = "corr-1") -> OrderRequest:
    return OrderRequest(
        correlation_id=correlation_id,
        symbol=_SYMBOL,
        side=side,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


@pytest.mark.asyncio
async def test_closes_opposite_position_before_submitting() -> None:
    connector = FakeConnector(fill_price=1.10)
    connector.positions = [
        Position(
            position_id="pos-1",
            symbol=_SYMBOL,
            side=OrderSide.BUY,
            volume=0.1,
            open_price=1.09,
        )
    ]
    engine = FlipSafeExecutionEngine(connector, LiveExecutionEngine(connector, EventBus()))

    ack = await engine.submit_order(_order(OrderSide.SELL))

    assert connector.closed_position_ids == ["pos-1"]
    assert ack.status == OrderStatus.FILLED
    assert len(connector.submitted_requests) == 1


@pytest.mark.asyncio
async def test_does_not_close_same_side_position() -> None:
    connector = FakeConnector(fill_price=1.10)
    connector.positions = [
        Position(
            position_id="pos-1",
            symbol=_SYMBOL,
            side=OrderSide.BUY,
            volume=0.1,
            open_price=1.09,
        )
    ]
    engine = FlipSafeExecutionEngine(connector, LiveExecutionEngine(connector, EventBus()))

    await engine.submit_order(_order(OrderSide.BUY))

    assert connector.closed_position_ids == []


@pytest.mark.asyncio
async def test_does_not_close_position_for_a_different_symbol() -> None:
    connector = FakeConnector(fill_price=1.10)
    connector.positions = [
        Position(
            position_id="pos-1",
            symbol=Symbol(name="GBPUSD"),
            side=OrderSide.BUY,
            volume=0.1,
            open_price=1.25,
        )
    ]
    engine = FlipSafeExecutionEngine(connector, LiveExecutionEngine(connector, EventBus()))

    await engine.submit_order(_order(OrderSide.SELL))

    assert connector.closed_position_ids == []


@pytest.mark.asyncio
async def test_no_open_positions_just_submits() -> None:
    connector = FakeConnector(fill_price=1.10)
    engine = FlipSafeExecutionEngine(connector, LiveExecutionEngine(connector, EventBus()))

    ack = await engine.submit_order(_order(OrderSide.BUY))

    assert connector.closed_position_ids == []
    assert ack.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_cancel_order_delegates_to_inner() -> None:
    connector = FakeConnector(fill_price=1.10)
    inner = LiveExecutionEngine(connector, EventBus())
    engine = FlipSafeExecutionEngine(connector, inner)

    with pytest.raises(NotImplementedError):
        await engine.cancel_order("corr-1")
