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
    max_drawdown_percent: float | None = None,
    max_correlation: float | None = None,
    max_spread: float | None = None,
    max_exposure: float | None = None,
    min_risk_reward_ratio: float | None = None,
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
        max_drawdown_percent=max_drawdown_percent,
        max_correlation=max_correlation,
        max_spread=max_spread,
        max_exposure=max_exposure,
        min_risk_reward_ratio=min_risk_reward_ratio,
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


# -- Phase 5 filters ------------------------------------------------------


def test_rejects_invalid_phase5_construction_parameters() -> None:
    event_bus = EventBus()
    portfolio = PortfolioEngine(PositionManager(OrderManager(event_bus), event_bus))
    base = {"max_open_positions": 1, "daily_loss_limit": 100.0}
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, **base, max_drawdown_percent=0.0)
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, **base, max_drawdown_percent=100.0)
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, **base, max_correlation=0.0)
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, **base, max_correlation=1.5)
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, **base, max_spread=0.0)
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, **base, max_exposure=0.0)
    with pytest.raises(ValueError):
        RiskEngine(portfolio, event_bus, **base, min_risk_reward_ratio=0.0)


@pytest.mark.asyncio
async def test_max_drawdown_engages_kill_switch_off_the_running_peak() -> None:
    event_bus, risk, _ = _make_engine(
        daily_loss_limit=1_000_000.0,  # keep the daily-loss gate out of the way
        max_drawdown_percent=10.0,
        clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)),
    )

    await event_bus.publish(AccountStateChanged(account_state=_account_state(10_000.0)))
    await event_bus.publish(AccountStateChanged(account_state=_account_state(11_000.0)))
    assert not risk.is_kill_switch_engaged()  # new peak, no drawdown yet

    await event_bus.publish(AccountStateChanged(account_state=_account_state(10_500.0)))
    assert not risk.is_kill_switch_engaged()  # ~4.5% off the 11,000 peak, under 10%

    await event_bus.publish(AccountStateChanged(account_state=_account_state(9_800.0)))
    assert risk.is_kill_switch_engaged()  # ~10.9% off the 11,000 peak
    assert risk.kill_switch_reason is not None


@pytest.mark.asyncio
async def test_max_drawdown_disabled_by_default() -> None:
    event_bus, risk, _ = _make_engine(daily_loss_limit=1_000_000.0)

    await event_bus.publish(AccountStateChanged(account_state=_account_state(10_000.0)))
    await event_bus.publish(AccountStateChanged(account_state=_account_state(1_000.0)))

    assert not risk.is_kill_switch_engaged()


def test_evaluate_correlation_passes_when_disabled() -> None:
    _, risk, _ = _make_engine()

    assert risk.evaluate_correlation(
        "EURUSD", correlation_matrix={"EURUSD": {"GBPUSD": 0.99}}, open_symbols=["GBPUSD"]
    )


def test_evaluate_correlation_rejects_a_highly_correlated_open_symbol() -> None:
    _, risk, _ = _make_engine(max_correlation=0.8)
    matrix = {"EURUSD": {"EURUSD": 1.0, "GBPUSD": 0.9}, "GBPUSD": {"EURUSD": 0.9, "GBPUSD": 1.0}}

    assert not risk.evaluate_correlation(
        "EURUSD", correlation_matrix=matrix, open_symbols=["GBPUSD"]
    )


def test_evaluate_correlation_passes_a_weakly_correlated_open_symbol() -> None:
    _, risk, _ = _make_engine(max_correlation=0.8)
    matrix = {"EURUSD": {"EURUSD": 1.0, "USDJPY": 0.1}, "USDJPY": {"EURUSD": 0.1, "USDJPY": 1.0}}

    assert risk.evaluate_correlation(
        "EURUSD", correlation_matrix=matrix, open_symbols=["USDJPY"]
    )


def test_evaluate_correlation_ignores_the_symbol_itself_in_open_symbols() -> None:
    _, risk, _ = _make_engine(max_correlation=0.8)
    matrix = {"EURUSD": {"EURUSD": 1.0}}

    assert risk.evaluate_correlation(
        "EURUSD", correlation_matrix=matrix, open_symbols=["EURUSD"]
    )


def test_evaluate_correlation_passes_when_symbol_missing_from_matrix() -> None:
    _, risk, _ = _make_engine(max_correlation=0.8)

    assert risk.evaluate_correlation("EURUSD", correlation_matrix={}, open_symbols=["GBPUSD"])


def test_evaluate_spread_passes_when_disabled() -> None:
    _, risk, _ = _make_engine()

    assert risk.evaluate_spread(10.0)


def test_evaluate_spread_rejects_a_spread_beyond_the_maximum() -> None:
    _, risk, _ = _make_engine(max_spread=0.0003)

    assert risk.evaluate_spread(0.0002)
    assert not risk.evaluate_spread(0.0004)


def test_evaluate_exposure_passes_when_disabled() -> None:
    _, risk, _ = _make_engine()

    assert risk.evaluate_exposure(current_exposure=1_000.0, additional_volume=1_000.0)


def test_evaluate_exposure_rejects_when_the_cap_would_be_exceeded() -> None:
    _, risk, _ = _make_engine(max_exposure=1.0)

    assert risk.evaluate_exposure(current_exposure=0.5, additional_volume=0.4)
    assert not risk.evaluate_exposure(current_exposure=0.5, additional_volume=0.6)


def test_evaluate_min_risk_reward_passes_when_disabled() -> None:
    _, risk, _ = _make_engine()

    assert risk.evaluate_min_risk_reward(None)
    assert risk.evaluate_min_risk_reward(0.1)


def test_evaluate_min_risk_reward_rejects_below_the_minimum_or_missing() -> None:
    _, risk, _ = _make_engine(min_risk_reward_ratio=1.5)

    assert risk.evaluate_min_risk_reward(1.5)
    assert risk.evaluate_min_risk_reward(2.0)
    assert not risk.evaluate_min_risk_reward(1.4)
    assert not risk.evaluate_min_risk_reward(None)
