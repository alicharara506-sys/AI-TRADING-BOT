from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.execution.risk_gate import RiskGatedExecutionEngine
from core.interfaces.events import TickReceived
from core.interfaces.types import OrderRequest, OrderSide, OrderStatus, OrderType, Symbol, Tick
from core.portfolio.engine import PortfolioEngine
from core.portfolio.position_manager import PositionManager
from core.risk.engine import RiskEngine
from execution_backends.backtest.engine import BacktestExecutionEngine

_SYMBOL = Symbol(name="EURUSD")


def _market_order(correlation_id: str) -> OrderRequest:
    return OrderRequest(
        correlation_id=correlation_id,
        symbol=_SYMBOL,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


@pytest.mark.asyncio
async def test_risk_engine_vetoes_second_order_once_at_max_positions() -> None:
    """Phase 5's exit criteria: the Risk Engine sits in the event path, not beside
    it. A second order that would breach max_open_positions is vetoed before the
    Execution Engine -- and therefore the venue -- ever sees it, using the real
    RiskEngine and real Portfolio/Position state, not a stand-in.
    """
    event_bus = EventBus()
    order_manager = OrderManager(event_bus)
    position_manager = PositionManager(order_manager, event_bus)
    portfolio = PortfolioEngine(position_manager)
    risk_engine = RiskEngine(portfolio, event_bus, max_open_positions=1, daily_loss_limit=1_000.0)
    backtest_engine = BacktestExecutionEngine(event_bus)
    gated_engine = RiskGatedExecutionEngine(backtest_engine, risk_engine, event_bus)

    await event_bus.publish(
        TickReceived(
            tick=Tick(
                symbol=_SYMBOL,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                bid=1.0998,
                ask=1.1000,
            )
        )
    )

    first_ack = await gated_engine.submit_order(_market_order("first"))

    assert first_ack.status == OrderStatus.FILLED
    assert portfolio.open_position_count() == 1

    second_ack = await gated_engine.submit_order(_market_order("second"))

    assert second_ack.status == OrderStatus.REJECTED
    assert "Risk Engine" in (second_ack.reason or "")
    # The order never reached the Execution Engine (and therefore never reached
    # the venue) -- but the Order Manager still has a complete, honest record of
    # the attempt: submitted, then rejected by the Risk Engine, not the venue.
    second_order = order_manager.get_order("second")
    assert second_order is not None
    assert second_order.status == OrderStatus.REJECTED
    assert second_order.reason == "Vetoed by Risk Engine"
    assert portfolio.open_position_count() == 1
