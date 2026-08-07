from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backtesting.validation.look_ahead import LookAheadBiasCheck
from backtesting.validation.monte_carlo import MonteCarloCheck
from backtesting.validation.pipeline import ValidationPipeline
from backtesting.validation.walk_forward import WalkForwardCheck
from core.execution.order import Order
from core.interfaces.types import (
    Bar,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    Timeframe,
)
from core.risk.sizing import FixedVolumeSizingModel
from live_trading.preflight import pair_round_trip_returns, run_preflight_backtest
from strategies.simple.sma_crossover import SmaCrossoverStrategy
from tests.support.fake_strategy import AlwaysFlipStrategy

_SYMBOL = Symbol(name="EURUSD")
# The exact same in-sample/out-of-sample-stable, bounded-drawdown profile
# already verified passing in test_validation_gate_enforcement.py.
_ROBUST_RETURNS: list[float] = [
    10, -4, 8, -3, 9, -5, 7, -2, 10, -4, 9, -5, 8, -3, 7, -4, 10, -2, 9, -3,
]


def _order(correlation_id: str, side: OrderSide, fill_price: float, volume: float = 1.0) -> Order:
    order = Order(
        request=OrderRequest(
            correlation_id=correlation_id,
            symbol=_SYMBOL,
            side=side,
            order_type=OrderType.MARKET,
            volume=volume,
        )
    )
    order.status = OrderStatus.FILLED
    order.fill_price = fill_price
    return order


def _pipeline() -> ValidationPipeline:
    return ValidationPipeline(
        walk_forward=WalkForwardCheck(max_degradation=0.5),
        monte_carlo=MonteCarloCheck(max_drawdown=30.0, iterations=500, seed=1),
        look_ahead=LookAheadBiasCheck(),
    )


def test_pair_round_trip_returns_buy_then_sell() -> None:
    orders = [_order("1", OrderSide.BUY, 1.10), _order("2", OrderSide.SELL, 1.12)]

    assert pair_round_trip_returns(orders) == pytest.approx([0.02])


def test_pair_round_trip_returns_sell_then_buy() -> None:
    orders = [_order("1", OrderSide.SELL, 1.10), _order("2", OrderSide.BUY, 1.08)]

    assert pair_round_trip_returns(orders) == pytest.approx([0.02])


def test_pair_round_trip_returns_ignores_unfilled_orders() -> None:
    rejected = _order("2", OrderSide.SELL, 1.12)
    rejected.status = OrderStatus.REJECTED
    orders = [_order("1", OrderSide.BUY, 1.10), rejected, _order("3", OrderSide.SELL, 1.15)]

    assert pair_round_trip_returns(orders) == pytest.approx([0.05])


def test_pair_round_trip_returns_dangling_open_order_contributes_nothing() -> None:
    orders = [_order("1", OrderSide.BUY, 1.10)]

    assert pair_round_trip_returns(orders) == []


def _bars_for_returns(returns: list[float]) -> list[Bar]:
    """Inverse of the (BUY-open->close_{i+1}-close_i, SELL-open->close_i-
    close_{i+1}) round-trip formula AlwaysFlipStrategy + zero spread produces
    -- lets a test assert on an exact, pre-verified-passing returns profile
    without needing to reverse-engineer SMA crossovers.
    """
    closes = [100.0]
    for i, pnl in enumerate(returns):
        closes.append(closes[-1] + pnl if i % 2 == 0 else closes[-1] - pnl)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M15,
            timestamp=start + timedelta(minutes=15 * i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=0.0,
        )
        for i, close in enumerate(closes)
    ]


@pytest.mark.asyncio
async def test_run_preflight_backtest_reproduces_a_known_robust_profile() -> None:
    bars = _bars_for_returns(_ROBUST_RETURNS)

    report, trade_returns = await run_preflight_backtest(
        AlwaysFlipStrategy,
        bars,
        strategy_name="always_flip",
        starting_equity=10_000.0,
        sizing_model=FixedVolumeSizingModel(1.0),
        pipeline=_pipeline(),
        spread=0.0,
    )

    assert trade_returns == pytest.approx(_ROBUST_RETURNS)
    assert report.passed


@pytest.mark.asyncio
async def test_run_preflight_backtest_fails_a_strategy_with_too_few_trades() -> None:
    # The same verified fast=2/slow=4 SMA crossover trace used in
    # SmaCrossoverStrategy's own unit tests: exactly 2 trades, well under the
    # 10-trade minimum the Validation Pipeline requires.
    closes = [1.00, 0.95, 0.90, 0.95, 1.05, 1.15, 1.25, 1.20, 1.10, 1.00, 0.90]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=start + timedelta(minutes=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=0.0,
        )
        for i, close in enumerate(closes)
    ]

    report, trade_returns = await run_preflight_backtest(
        lambda: SmaCrossoverStrategy(fast_period=2, slow_period=4),
        bars,
        strategy_name="sma_crossover",
        starting_equity=10_000.0,
        sizing_model=FixedVolumeSizingModel(0.1),
        pipeline=_pipeline(),
    )

    assert len(trade_returns) == 1
    assert not report.passed


@pytest.mark.asyncio
async def test_run_preflight_backtest_rejects_too_few_bars() -> None:
    with pytest.raises(ValueError):
        await run_preflight_backtest(
            AlwaysFlipStrategy,
            [],
            strategy_name="always_flip",
            starting_equity=10_000.0,
            sizing_model=FixedVolumeSizingModel(1.0),
            pipeline=_pipeline(),
        )
