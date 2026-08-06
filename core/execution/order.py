from __future__ import annotations

from dataclasses import dataclass

from core.interfaces.types import OrderRequest, OrderStatus

_ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.SUBMITTED, OrderStatus.REJECTED}),
    OrderStatus.SUBMITTED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED}
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
}


class InvalidOrderTransition(Exception):
    pass


@dataclass
class Order:
    """Venue-independent order lifecycle state, driven purely by Event Bus events
    (OrderSubmitted/OrderFilled/OrderRejected) -- never by a direct venue call."""

    request: OrderRequest
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: str | None = None
    fill_price: float | None = None
    reason: str | None = None

    def transition_to(self, new_status: OrderStatus) -> None:
        if new_status == self.status:
            return
        allowed = _ALLOWED_TRANSITIONS[self.status]
        if new_status not in allowed:
            raise InvalidOrderTransition(
                f"Order '{self.request.correlation_id}' cannot transition "
                f"from {self.status} to {new_status}"
            )
        self.status = new_status


__all__ = ["InvalidOrderTransition", "Order"]
