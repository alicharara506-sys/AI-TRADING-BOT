from __future__ import annotations

import pytest

from core.event_bus.bus import EventBus
from core.execution.risk_gate import RiskGatedExecutionEngine
from core.interfaces.events import OrderRejected, OrderSubmitted
from core.interfaces.types import (
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
    TradeSignal,
)
from execution_backends.live.engine import LiveExecutionEngine
from tests.support.fake_connector import FakeConnector


class _AlwaysVetoRiskModel:
    def evaluate_signal(self, signal: TradeSignal) -> TradeSignal | None:
        return None

    def evaluate_order(self, request: OrderRequest) -> OrderRequest | None:
        return None


class _AlwaysApproveRiskModel:
    def evaluate_signal(self, signal: TradeSignal) -> TradeSignal | None:
        return signal

    def evaluate_order(self, request: OrderRequest) -> OrderRequest | None:
        return request


def _order() -> OrderRequest:
    return OrderRequest(
        correlation_id="corr-1",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


@pytest.mark.asyncio
async def test_vetoed_order_never_reaches_inner_engine() -> None:
    event_bus = EventBus()
    connector = FakeConnector()
    inner = LiveExecutionEngine(connector, event_bus)
    gated = RiskGatedExecutionEngine(inner, _AlwaysVetoRiskModel(), event_bus)

    submitted: list[OrderSubmitted] = []
    rejected: list[OrderRejected] = []
    event_bus.subscribe(OrderSubmitted, lambda e: submitted.append(e))
    event_bus.subscribe(OrderRejected, lambda e: rejected.append(e))

    ack = await gated.submit_order(_order())

    assert ack.status == OrderStatus.REJECTED
    assert connector.submitted_requests == []  # the venue was never called
    # The gate itself publishes OrderSubmitted for a vetoed order (nothing else
    # will), so the Order Manager still records a complete submitted-then-rejected
    # history instead of a rejection with no prior record.
    assert len(submitted) == 1
    assert len(rejected) == 1


@pytest.mark.asyncio
async def test_approved_order_reaches_inner_engine() -> None:
    event_bus = EventBus()
    connector = FakeConnector(fill_price=1.1000)
    inner = LiveExecutionEngine(connector, event_bus)
    gated = RiskGatedExecutionEngine(inner, _AlwaysApproveRiskModel(), event_bus)

    ack = await gated.submit_order(_order())

    assert ack.status == OrderStatus.FILLED
    assert len(connector.submitted_requests) == 1


@pytest.mark.asyncio
async def test_cancel_order_delegates_to_inner_engine() -> None:
    event_bus = EventBus()
    connector = FakeConnector()
    inner = LiveExecutionEngine(connector, event_bus)
    gated = RiskGatedExecutionEngine(inner, _AlwaysApproveRiskModel(), event_bus)

    with pytest.raises(NotImplementedError):
        await gated.cancel_order("corr-1")
