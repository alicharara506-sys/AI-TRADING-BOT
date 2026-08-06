from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.interfaces.events import TickReceived
from core.interfaces.execution import ExecutionEngine
from core.interfaces.types import (
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    Tick,
)
from execution_backends.backtest.engine import BacktestExecutionEngine
from execution_backends.live.engine import LiveExecutionEngine
from tests.support.fake_connector import FakeConnector

_SYMBOL = Symbol(name="EURUSD")
_VOLUME = 0.1


async def _always_buy_then_close(
    execution_engine: ExecutionEngine,
) -> tuple[OrderAck, OrderAck]:
    """The Phase 4 strategy stub: buy, then immediately close by selling the same
    volume. The Strategy/Signal/Risk/Portfolio engines don't exist until later
    phases -- this coroutine is deliberately the only "strategy" in the system
    right now, and it is driven, unmodified, by two different ExecutionEngine
    implementations. Proving that substitution is what Phase 4's exit criteria
    is actually about.
    """
    buy_ack = await execution_engine.submit_order(
        OrderRequest(
            correlation_id="buy-1",
            symbol=_SYMBOL,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            volume=_VOLUME,
        )
    )
    sell_ack = await execution_engine.submit_order(
        OrderRequest(
            correlation_id="sell-1",
            symbol=_SYMBOL,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            volume=_VOLUME,
        )
    )
    return buy_ack, sell_ack


@pytest.mark.asyncio
async def test_backtest_and_live_engines_drive_identical_order_manager_outcomes() -> None:
    # -- backtest run: BacktestExecutionEngine, fed by a TickReceived event exactly
    # like a Parquet replay would produce --
    backtest_bus = EventBus()
    backtest_manager = OrderManager(backtest_bus)
    backtest_engine = BacktestExecutionEngine(backtest_bus)
    await backtest_bus.publish(
        TickReceived(
            tick=Tick(
                symbol=_SYMBOL,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                bid=1.0998,
                ask=1.1000,
            )
        )
    )

    backtest_buy_ack, backtest_sell_ack = await _always_buy_then_close(backtest_engine)

    # -- live run: identical strategy-stub coroutine, only the ExecutionEngine
    # (and its Connector) differ --
    live_bus = EventBus()
    live_manager = OrderManager(live_bus)
    live_engine = LiveExecutionEngine(FakeConnector(fill_price=1.1000), live_bus)

    live_buy_ack, live_sell_ack = await _always_buy_then_close(live_engine)

    # Both engines fill both orders -- the mechanism is consistent regardless of
    # which venue (simulated or real) sits behind the ExecutionEngine interface.
    for buy_ack, sell_ack in (
        (backtest_buy_ack, backtest_sell_ack),
        (live_buy_ack, live_sell_ack),
    ):
        assert buy_ack.status == OrderStatus.FILLED
        assert sell_ack.status == OrderStatus.FILLED

    # The Order Manager -- the venue-independent source of truth -- ends up in the
    # identical shape either way: two orders, submitted in order, both filled.
    for manager in (backtest_manager, live_manager):
        orders = manager.list_orders()
        assert [order.request.correlation_id for order in orders] == ["buy-1", "sell-1"]
        assert [order.status for order in orders] == [OrderStatus.FILLED, OrderStatus.FILLED]

    # Backtest fills are explainable purely by the spread: bought at ask, closed
    # at bid, cost is exactly the spread and nothing else (no hidden slippage).
    backtest_buy_order = backtest_manager.get_order("buy-1")
    backtest_sell_order = backtest_manager.get_order("sell-1")
    assert backtest_buy_order is not None
    assert backtest_sell_order is not None
    assert backtest_buy_order.fill_price == pytest.approx(1.1000)
    assert backtest_sell_order.fill_price == pytest.approx(1.0998)
