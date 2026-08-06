from __future__ import annotations

import pytest

from core.event_bus.bus import EventBus
from core.execution.validation_gate import ValidationError, ValidationGatedExecutionEngine
from core.interfaces.types import OrderRequest, OrderSide, OrderStatus, OrderType, Symbol
from core.interfaces.validation import CheckResult, ValidationReport
from execution_backends.live.engine import LiveExecutionEngine
from tests.support.fake_connector import FakeConnector


def _report(*, passed: bool) -> ValidationReport:
    return ValidationReport(
        strategy_name="sma_crossover",
        checks=(CheckResult(name="walk_forward", passed=passed),),
    )


def _order() -> OrderRequest:
    return OrderRequest(
        correlation_id="corr-1",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


def test_failing_report_prevents_construction() -> None:
    inner = LiveExecutionEngine(FakeConnector(), EventBus())

    with pytest.raises(ValidationError) as excinfo:
        ValidationGatedExecutionEngine(inner, _report(passed=False))

    assert "sma_crossover" in str(excinfo.value)
    assert "walk_forward" in str(excinfo.value)


@pytest.mark.asyncio
async def test_passing_report_allows_construction_and_execution() -> None:
    inner = LiveExecutionEngine(FakeConnector(fill_price=1.1), EventBus())
    gated = ValidationGatedExecutionEngine(inner, _report(passed=True))

    ack = await gated.submit_order(_order())

    assert ack.status == OrderStatus.FILLED
    assert gated.report.passed is True


@pytest.mark.asyncio
async def test_cancel_order_delegates_to_inner_engine() -> None:
    # LiveExecutionEngine doesn't support cancellation yet (Phase 4); the gate
    # must delegate transparently, not swallow or reinterpret that behavior.
    inner = LiveExecutionEngine(FakeConnector(), EventBus())
    gated = ValidationGatedExecutionEngine(inner, _report(passed=True))

    with pytest.raises(NotImplementedError):
        await gated.cancel_order("corr-1")
