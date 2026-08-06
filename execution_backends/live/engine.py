from __future__ import annotations

from core.event_bus.bus import EventBus
from core.interfaces.connector import Connector
from core.interfaces.events import OrderFilled, OrderRejected, OrderSubmitted
from core.interfaces.types import OrderAck, OrderRequest, OrderStatus


class LiveExecutionEngine:
    """ExecutionEngine backed by a real venue Connector (MT4/MT5 today). Strategy,
    Signal, Portfolio, and Risk Engine code is identical to the backtest path --
    only this class and the data source differ, per the architecture's
    backtest/live-parity requirement.
    """

    def __init__(self, connector: Connector, event_bus: EventBus) -> None:
        self._connector = connector
        self._event_bus = event_bus

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        await self._event_bus.publish(OrderSubmitted(request=request))
        ack = await self._connector.submit_order(request)
        if ack.status == OrderStatus.FILLED:
            await self._event_bus.publish(OrderFilled(ack=ack))
        else:
            await self._event_bus.publish(OrderRejected(ack=ack))
        return ack

    async def cancel_order(self, correlation_id: str) -> None:
        # The Connector Protocol has no pending-order cancellation call yet --
        # only submit/modify/close. Wiring this up belongs to the pending-order
        # support the roadmap adds alongside full Order Manager cancellation flow.
        raise NotImplementedError("Order cancellation is not yet supported")


__all__ = ["LiveExecutionEngine"]
