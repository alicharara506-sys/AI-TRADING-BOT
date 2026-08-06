from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.interfaces.clock import Clock
from core.interfaces.events import AccountStateChanged, OrderFilled, OrderSubmitted
from core.interfaces.types import (
    AccountState,
    Direction,
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    TradeSignal,
)
from core.kernel.clock import TestClock
from core.portfolio.engine import PortfolioEngine
from core.portfolio.position_manager import PositionManager
from core.risk.engine import RiskEngine

_SYMBOL = Symbol(name="EURUSD")


def _account_state(equity: float) -> AccountState:
    return AccountState(
        balance=equity,
        equity=equity,
        margin=0.0,
        free_margin=equity,
        margin_level=None,
        currency="USD",
    )


def _signal() -> TradeSignal:
    return TradeSignal(
        symbol=_SYMBOL,
        direction=Direction.LONG,
        combined_confidence=0.9,
        threshold=0.6,
        evidence=(),
    )


def _order(correlation_id: str = "corr-1") -> OrderRequest:
    return OrderRequest(
        correlation_id=correlation_id,
        symbol=_SYMBOL,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


def _make_engine(
    *,
    max_open_positions: int = 3,
    daily_loss_limit: float = 500.0,
    clock: Clock | None = None,
) -> tuple[EventBus, RiskEngine, PortfolioEngine]:
    event_bus = EventBus()
    order_manager = OrderManager(event_bus)
    position_manager = PositionManager(order_manager, event_bus)
    portfolio = PortfolioEngine(position_manager)
    risk = RiskEngine(
        portfolio,
        event_bus,
        max_open_positions=max_open_positions,
        daily_loss_limit=daily_loss_limit,
        clock=clock,
    )
    return event_bus, risk, portfolio


def test_rejects_invalid_construction_parameters() -> None:
    event_bus = EventBus()
    portfolio = PortfolioEngine(PositionManager(OrderManager(event_bus), event_bus))
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, max_open_positions=0, daily_loss_limit=100.0)
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, max_open_positions=1, daily_loss_limit=0.0)


def test_approves_signal_and_order_by_default() -> None:
    _, risk, _ = _make_engine()

    assert risk.evaluate_signal(_signal()) is not None
    assert risk.evaluate_order(_order()) is not None


def test_kill_switch_vetoes_everything() -> None:
    _, risk, _ = _make_engine()
    risk.engage_kill_switch("manual halt")

    assert risk.is_kill_switch_engaged()
    assert risk.evaluate_signal(_signal()) is None
    assert risk.evaluate_order(_order()) is None


def test_reset_kill_switch_restores_approval() -> None:
    _, risk, _ = _make_engine()
    risk.engage_kill_switch("manual halt")
    risk.reset_kill_switch()

    assert not risk.is_kill_switch_engaged()
    assert risk.evaluate_order(_order()) is not None


@pytest.mark.asyncio
async def test_max_open_positions_vetoes_once_at_capacity() -> None:
    event_bus, risk, _portfolio = _make_engine(max_open_positions=1)
    await event_bus.publish(OrderSubmitted(request=_order()))
    await event_bus.publish(
        OrderFilled(
            ack=OrderAck(
                correlation_id="corr-1",
                broker_order_id="b-1",
                status=OrderStatus.FILLED,
                fill_price=1.1000,
            )
        )
    )

    assert risk.evaluate_order(_order("corr-2")) is None
    assert risk.evaluate_signal(_signal()) is None


@pytest.mark.asyncio
async def test_daily_loss_limit_engages_kill_switch() -> None:
    event_bus, risk, _ = _make_engine(
        daily_loss_limit=100.0, clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC))
    )

    await event_bus.publish(AccountStateChanged(account_state=_account_state(10_000.0)))
    assert not risk.is_kill_switch_engaged()

    await event_bus.publish(AccountStateChanged(account_state=_account_state(9_850.0)))
    assert risk.is_kill_switch_engaged()
    assert risk.kill_switch_reason is not None


@pytest.mark.asyncio
async def test_daily_loss_baseline_resets_on_new_day() -> None:
    clock = TestClock(datetime(2026, 1, 1, tzinfo=UTC))
    event_bus, risk, _ = _make_engine(daily_loss_limit=100.0, clock=clock)

    await event_bus.publish(AccountStateChanged(account_state=_account_state(10_000.0)))
    await event_bus.publish(AccountStateChanged(account_state=_account_state(9_950.0)))
    assert not risk.is_kill_switch_engaged()

    clock.advance(timedelta(days=1))
    await event_bus.publish(AccountStateChanged(account_state=_account_state(9_950.0)))
    assert not risk.is_kill_switch_engaged()  # new day resets the baseline to 9950

    await event_bus.publish(AccountStateChanged(account_state=_account_state(9_800.0)))
    assert risk.is_kill_switch_engaged()
