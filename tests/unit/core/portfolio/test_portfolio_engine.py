from __future__ import annotations

import pytest

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.interfaces.events import OrderFilled, OrderSubmitted
from core.interfaces.types import (
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Symbol,
)
from core.portfolio.engine import PortfolioEngine
from core.portfolio.position_manager import PositionManager

_EURUSD = Symbol(name="EURUSD")
_GBPUSD = Symbol(name="GBPUSD")


async def _open(
    event_bus: EventBus,
    symbol: Symbol,
    correlation_id: str,
    side: OrderSide,
    volume: float,
    price: float,
) -> None:
    await event_bus.publish(
        OrderSubmitted(
            request=OrderRequest(
                correlation_id=correlation_id,
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                volume=volume,
            )
        )
    )
    await event_bus.publish(
        OrderFilled(
            ack=OrderAck(
                correlation_id=correlation_id,
                broker_order_id=f"b-{correlation_id}",
                status=OrderStatus.FILLED,
                fill_price=price,
            )
        )
    )


@pytest.mark.asyncio
async def test_exposure_and_position_count_across_symbols() -> None:
    event_bus = EventBus()
    order_manager = OrderManager(event_bus)
    position_manager = PositionManager(order_manager, event_bus)
    portfolio = PortfolioEngine(position_manager)

    await _open(event_bus, _EURUSD, "buy-1", OrderSide.BUY, 0.3, 1.1000)
    await _open(event_bus, _GBPUSD, "sell-1", OrderSide.SELL, 0.2, 1.2500)

    assert portfolio.open_position_count() == 2
    assert portfolio.signed_exposure(_EURUSD) == pytest.approx(0.3)
    assert portfolio.signed_exposure(_GBPUSD) == pytest.approx(-0.2)
    assert portfolio.total_exposure() == pytest.approx(0.5)
    assert portfolio.get_position(Symbol(name="USDJPY")) is None
