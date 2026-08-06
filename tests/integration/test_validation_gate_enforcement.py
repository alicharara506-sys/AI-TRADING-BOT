from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backtesting.validation.look_ahead import LookAheadBiasCheck
from backtesting.validation.monte_carlo import MonteCarloCheck
from backtesting.validation.pipeline import ValidationPipeline
from backtesting.validation.walk_forward import WalkForwardCheck
from core.event_bus.bus import EventBus
from core.execution.validation_gate import ValidationError, ValidationGatedExecutionEngine
from core.interfaces.types import OrderRequest, OrderSide, OrderStatus, OrderType, Symbol
from execution_backends.live.engine import LiveExecutionEngine
from tests.support.fake_connector import FakeConnector

_SYMBOL = Symbol(name="EURUSD")
# Verified in this phase's own validation unit tests: similar in-sample/
# out-of-sample profile (zero degradation) and a tail drawdown comfortably
# inside a 30.0 limit.
_ROBUST_RETURNS = [10, -4, 8, -3, 9, -5, 7, -2, 10, -4, 9, -5, 8, -3, 7, -4, 10, -2, 9, -3]


def _pipeline() -> ValidationPipeline:
    return ValidationPipeline(
        walk_forward=WalkForwardCheck(max_degradation=0.5),
        monte_carlo=MonteCarloCheck(max_drawdown=30.0, iterations=500, seed=1),
        look_ahead=LookAheadBiasCheck(),
    )


def _order() -> OrderRequest:
    return OrderRequest(
        correlation_id="corr-1",
        symbol=_SYMBOL,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


@pytest.mark.asyncio
async def test_unvalidated_strategy_cannot_be_wired_to_live_execution() -> None:
    """Phase 8's exit criteria: a strategy cannot reach mode=live without a
    passing Validation Report -- enforced structurally (construction itself
    raises), not left as a step someone has to remember to run.
    """
    pipeline = _pipeline()
    timestamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(20)]

    # Too few trades to walk-forward split meaningfully -> the report fails.
    failing_report = pipeline.run(
        strategy_name="undertested_strategy",
        trade_returns=[10.0, -4.0, 8.0],
        bar_timestamps=timestamps,
    )
    assert not failing_report.passed

    live_engine = LiveExecutionEngine(FakeConnector(fill_price=1.1), EventBus())
    with pytest.raises(ValidationError):
        ValidationGatedExecutionEngine(live_engine, failing_report)

    # A robust, walk-forward-stable trade history -> the report passes, and only
    # now can the exact same strategy be wired to live execution.
    passing_report = pipeline.run(
        strategy_name="undertested_strategy",
        trade_returns=_ROBUST_RETURNS,
        bar_timestamps=timestamps,
    )
    assert passing_report.passed

    gated_engine = ValidationGatedExecutionEngine(live_engine, passing_report)
    ack = await gated_engine.submit_order(_order())

    assert ack.status == OrderStatus.FILLED
