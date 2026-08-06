from __future__ import annotations

from core.event_bus.bus import EventBus
from core.execution.order import Order
from core.interfaces.events import OrderFilled, OrderRejected, OrderSubmitted
from core.interfaces.types import OrderStatus


class OrderManager:
    """Single source of truth for order lifecycle state, independent of which
    ExecutionEngine (backtest or live) is producing the events."""

    def __init__(self, event_bus: EventBus) -> None:
        self._orders: dict[str, Order] = {}
        event_bus.subscribe(OrderSubmitted, self._on_submitted)
        event_bus.subscribe(OrderFilled, self._on_filled)
        event_bus.subscribe(OrderRejected, self._on_rejected)

    async def _on_submitted(self, event: OrderSubmitted) -> None:
        correlation_id = event.request.correlation_id
        order = self._orders.get(correlation_id)
        if order is None:
            order = Order(request=event.request)
            self._orders[correlation_id] = order
        order.transition_to(OrderStatus.SUBMITTED)

    async def _on_filled(self, event: OrderFilled) -> None:
        order = self._require(event.ack.correlation_id)
        order.broker_order_id = event.ack.broker_order_id
        order.fill_price = event.ack.fill_price
        order.transition_to(OrderStatus.FILLED)

    async def _on_rejected(self, event: OrderRejected) -> None:
        order = self._require(event.ack.correlation_id)
        order.reason = event.ack.reason
        order.transition_to(OrderStatus.REJECTED)

    def _require(self, correlation_id: str) -> Order:
        order = self._orders.get(correlation_id)
        if order is None:
            raise KeyError(f"Unknown order '{correlation_id}'")
        return order

    def get_order(self, correlation_id: str) -> Order | None:
        return self._orders.get(correlation_id)

    def list_orders(self) -> list[Order]:
        return list(self._orders.values())


__all__ = ["OrderManager"]
