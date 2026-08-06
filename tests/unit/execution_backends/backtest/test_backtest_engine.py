from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.event_bus.bus import EventBus
from core.interfaces.events import OrderFilled, OrderRejected, TickReceived
from core.interfaces.types import (
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    Tick,
)
from execution_backends.backtest.engine import BacktestExecutionEngine


def _tick(symbol: Symbol, *, bid: float, ask: float) -> Tick:
    return Tick(symbol=symbol, timestamp=datetime(2026, 1, 1, tzinfo=UTC), bid=bid, ask=ask)


def _market_order(correlation_id: str, symbol: Symbol, side: OrderSide) -> OrderRequest:
    return OrderRequest(
        correlation_id=correlation_id,
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


@pytest.mark.asyncio
async def test_buy_fills_at_ask_and_sell_fills_at_bid() -> None:
    event_bus = EventBus()
    engine = BacktestExecutionEngine(event_bus)
    symbol = Symbol(name="EURUSD")
    await event_bus.publish(TickReceived(tick=_tick(symbol, bid=1.0998, ask=1.1000)))

    buy_ack = await engine.submit_order(_market_order("buy-1", symbol, OrderSide.BUY))
    sell_ack = await engine.submit_order(_market_order("sell-1", symbol, OrderSide.SELL))

    assert buy_ack.status == OrderStatus.FILLED
    assert buy_ack.fill_price == pytest.approx(1.1000)
    assert sell_ack.status == OrderStatus.FILLED
    assert sell_ack.fill_price == pytest.approx(1.0998)


@pytest.mark.asyncio
async def test_submit_without_market_data_rejects() -> None:
    event_bus = EventBus()
    engine = BacktestExecutionEngine(event_bus)
    symbol = Symbol(name="GBPUSD")

    rejected: list[OrderRejected] = []
    event_bus.subscribe(OrderRejected, lambda e: rejected.append(e))

    ack = await engine.submit_order(_market_order("buy-1", symbol, OrderSide.BUY))

    assert ack.status == OrderStatus.REJECTED
    assert len(rejected) == 1


@pytest.mark.asyncio
async def test_submit_non_market_order_raises() -> None:
    event_bus = EventBus()
    engine = BacktestExecutionEngine(event_bus)
    request = OrderRequest(
        correlation_id="limit-1",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        volume=0.1,
        price=1.05,
    )

    with pytest.raises(NotImplementedError):
        await engine.submit_order(request)


@pytest.mark.asyncio
async def test_fill_publishes_order_filled_event() -> None:
    event_bus = EventBus()
    engine = BacktestExecutionEngine(event_bus)
    symbol = Symbol(name="EURUSD")
    await event_bus.publish(TickReceived(tick=_tick(symbol, bid=1.0998, ask=1.1000)))

    filled: list[OrderFilled] = []
    event_bus.subscribe(OrderFilled, lambda e: filled.append(e))

    await engine.submit_order(_market_order("buy-1", symbol, OrderSide.BUY))

    assert len(filled) == 1
    assert filled[0].ack.fill_price == pytest.approx(1.1000)
