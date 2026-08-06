from __future__ import annotations

from core.event_bus.bus import EventBus
from core.interfaces.events import OrderFilled, OrderRejected, OrderSubmitted, TickReceived
from core.interfaces.types import OrderAck, OrderRequest, OrderSide, OrderStatus, OrderType, Tick


class BacktestExecutionEngine:
    """Simplest backtest fill model: market orders fill instantly at the current
    bid/ask (spread is the only execution cost modeled; no latency or partial
    fills yet -- those arrive as the Backtesting Engine gains fidelity).

    Consumes the same TickReceived events the Market Data Engine publishes during
    a replay run, so it needs no separate wiring to "know" the current price.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._latest_ticks: dict[str, Tick] = {}
        self._next_order_id = 1
        event_bus.subscribe(TickReceived, self._on_tick)

    async def _on_tick(self, event: TickReceived) -> None:
        self._latest_ticks[event.tick.symbol.canonical] = event.tick

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        if request.order_type is not OrderType.MARKET:
            raise NotImplementedError(
                "BacktestExecutionEngine currently only fills market orders"
            )

        await self._event_bus.publish(OrderSubmitted(request=request))

        tick = self._latest_ticks.get(request.symbol.canonical)
        if tick is None:
            ack = OrderAck(
                correlation_id=request.correlation_id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                reason=f"No market data for '{request.symbol.canonical}'",
            )
            await self._event_bus.publish(OrderRejected(ack=ack))
            return ack

        fill_price = tick.ask if request.side is OrderSide.BUY else tick.bid
        broker_order_id = str(self._next_order_id)
        self._next_order_id += 1

        ack = OrderAck(
            correlation_id=request.correlation_id,
            broker_order_id=broker_order_id,
            status=OrderStatus.FILLED,
            fill_price=fill_price,
        )
        await self._event_bus.publish(OrderFilled(ack=ack))
        return ack

    async def cancel_order(self, correlation_id: str) -> None:
        return None


__all__ = ["BacktestExecutionEngine"]
