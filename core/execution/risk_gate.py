from __future__ import annotations

from core.event_bus.bus import EventBus
from core.interfaces.events import OrderRejected, OrderSubmitted
from core.interfaces.execution import ExecutionEngine
from core.interfaces.risk import RiskModel
from core.interfaces.types import OrderAck, OrderRequest, OrderStatus


class RiskGatedExecutionEngine:
    """Wraps any ExecutionEngine with a RiskModel gate: no OrderRequest reaches the
    wrapped engine -- and therefore no venue, real or simulated -- without first
    passing risk evaluation. This is what makes "risk management must override
    every strategy" a structural guarantee rather than a convention every caller
    has to remember to honor.
    """

    def __init__(self, inner: ExecutionEngine, risk_model: RiskModel, event_bus: EventBus) -> None:
        self._inner = inner
        self._risk_model = risk_model
        self._event_bus = event_bus

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        approved = self._risk_model.evaluate_order(request)
        if approved is None:
            # Nothing downstream will ever publish OrderSubmitted for this order --
            # the inner engine (the only other publisher) never runs. Publish it
            # here so the Order Manager records a complete, honest lifecycle
            # (submitted, then rejected) rather than a rejection with no history.
            await self._event_bus.publish(OrderSubmitted(request=request))
            ack = OrderAck(
                correlation_id=request.correlation_id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                reason="Vetoed by Risk Engine",
            )
            await self._event_bus.publish(OrderRejected(ack=ack))
            return ack
        return await self._inner.submit_order(approved)

    async def cancel_order(self, correlation_id: str) -> None:
        await self._inner.cancel_order(correlation_id)


__all__ = ["RiskGatedExecutionEngine"]
