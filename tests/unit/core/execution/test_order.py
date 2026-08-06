from __future__ import annotations

import pytest

from core.execution.order import InvalidOrderTransition, Order
from core.interfaces.types import OrderRequest, OrderSide, OrderStatus, OrderType, Symbol


def _request() -> OrderRequest:
    return OrderRequest(
        correlation_id="corr-1",
        symbol=Symbol(name="EURUSD"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        volume=0.1,
    )


def test_order_starts_pending() -> None:
    order = Order(request=_request())
    assert order.status == OrderStatus.PENDING


def test_valid_transition_sequence() -> None:
    order = Order(request=_request())
    order.transition_to(OrderStatus.SUBMITTED)
    order.transition_to(OrderStatus.FILLED)
    assert order.status == OrderStatus.FILLED


def test_same_status_transition_is_a_noop() -> None:
    order = Order(request=_request())
    order.transition_to(OrderStatus.PENDING)
    assert order.status == OrderStatus.PENDING


def test_invalid_transition_raises() -> None:
    order = Order(request=_request())
    with pytest.raises(InvalidOrderTransition):
        order.transition_to(OrderStatus.FILLED)


def test_terminal_state_rejects_further_transitions() -> None:
    order = Order(request=_request())
    order.transition_to(OrderStatus.SUBMITTED)
    order.transition_to(OrderStatus.FILLED)
    with pytest.raises(InvalidOrderTransition):
        order.transition_to(OrderStatus.CANCELLED)


def test_partially_filled_can_progress_to_filled_or_stay_partial() -> None:
    order = Order(request=_request())
    order.transition_to(OrderStatus.SUBMITTED)
    order.transition_to(OrderStatus.PARTIALLY_FILLED)
    order.transition_to(OrderStatus.PARTIALLY_FILLED)
    order.transition_to(OrderStatus.FILLED)
    assert order.status == OrderStatus.FILLED
