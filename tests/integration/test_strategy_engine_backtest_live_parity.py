from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.execution.risk_gate import RiskGatedExecutionEngine
from core.interfaces.events import AccountStateChanged, BarClosed, TickReceived
from core.interfaces.execution import ExecutionEngine
from core.interfaces.types import (
    AccountState,
    Bar,
    OrderSide,
    OrderStatus,
    Symbol,
    Tick,
    Timeframe,
)
from core.portfolio.engine import PortfolioEngine
from core.portfolio.position_manager import PositionManager
from core.risk.engine import RiskEngine
from core.risk.sizing import FixedVolumeSizingModel
from core.strategy.engine import StrategyEngine
from execution_backends.backtest.engine import BacktestExecutionEngine
from execution_backends.live.engine import LiveExecutionEngine
from strategies.simple.sma_crossover import SmaCrossoverStrategy
from tests.support.fake_connector import FakeConnector

_SYMBOL = Symbol(name="EURUSD")
# The same verified fast=2/slow=4 SMA crossover trace used in the strategy's own
# unit tests: LONG at index 4, SHORT at index 8.
_CLOSES = [1.00, 0.95, 0.90, 0.95, 1.05, 1.15, 1.25, 1.20, 1.10, 1.00, 0.90]
_SPREAD = 0.0002


def _bar(close: float, index: int) -> Bar:
    return Bar(
        symbol=_SYMBOL,
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0,
    )


def _tick(close: float, index: int) -> Tick:
    return Tick(
        symbol=_SYMBOL,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
        bid=close - _SPREAD / 2,
        ask=close + _SPREAD / 2,
    )


async def _run(
    event_bus: EventBus, execution_engine: ExecutionEngine, *, feed_ticks: bool
) -> OrderManager:
    """Wires up the full signal->risk->size->execute path and replays the fixed
    bar sequence through it. `execution_engine` and `feed_ticks` are the only
    things that differ between the backtest and live runs below -- everything
    else (Strategy, Risk, Portfolio, sizing) is identical code.
    """
    order_manager = OrderManager(event_bus)
    position_manager = PositionManager(order_manager, event_bus)
    portfolio = PortfolioEngine(position_manager)
    risk_engine = RiskEngine(
        portfolio, event_bus, max_open_positions=10, daily_loss_limit=1_000_000.0
    )
    gated_engine = RiskGatedExecutionEngine(execution_engine, risk_engine, event_bus)
    strategy = SmaCrossoverStrategy(fast_period=2, slow_period=4)
    StrategyEngine(strategy, risk_engine, FixedVolumeSizingModel(0.1), gated_engine, event_bus)

    await event_bus.publish(
        AccountStateChanged(
            account_state=AccountState(
                balance=10_000.0,
                equity=10_000.0,
                margin=0.0,
                free_margin=10_000.0,
                margin_level=None,
                currency="USD",
            )
        )
    )

    for i, close in enumerate(_CLOSES):
        if feed_ticks:
            await event_bus.publish(TickReceived(tick=_tick(close, i)))
        await event_bus.publish(BarClosed(bar=_bar(close, i)))

    return order_manager


@pytest.mark.asyncio
async def test_same_strategy_produces_matching_trades_in_backtest_and_live() -> None:
    """Phase 6's exit criteria: a real, unmodified simple-mode strategy produces
    matching trades whether driven by the backtest or the live Execution Engine.
    """
    backtest_bus = EventBus()
    backtest_orders = await _run(
        backtest_bus, BacktestExecutionEngine(backtest_bus), feed_ticks=True
    )

    live_bus = EventBus()
    live_orders = await _run(
        live_bus, LiveExecutionEngine(FakeConnector(fill_price=1.0), live_bus), feed_ticks=False
    )

    backtest_list = backtest_orders.list_orders()
    live_list = live_orders.list_orders()

    assert len(backtest_list) == 2
    assert len(live_list) == 2

    backtest_sides = [order.request.side for order in backtest_list]
    live_sides = [order.request.side for order in live_list]

    assert backtest_sides == [OrderSide.BUY, OrderSide.SELL]
    assert live_sides == backtest_sides

    assert all(order.status == OrderStatus.FILLED for order in backtest_list)
    assert all(order.status == OrderStatus.FILLED for order in live_list)
