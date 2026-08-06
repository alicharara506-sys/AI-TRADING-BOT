from __future__ import annotations

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.interfaces.events import OrderFilled, PositionClosed
from core.interfaces.types import OrderAck, OrderRequest, Position, Symbol


class PositionManager:
    """Venue-independent position state, built purely from fills. Aggregates per
    symbol (netting model): a same-side fill averages into the position; an
    opposite-side fill reduces, exactly closes, or closes-and-reverses it.

    Reconciling this state against a connector's own position reports on
    reconnect (per the MT4/MT5 connector's fault-tolerance design) is a later
    phase's concern -- this is the kernel-side source of truth in the meantime.
    """

    def __init__(self, order_manager: OrderManager, event_bus: EventBus) -> None:
        self._order_manager = order_manager
        self._event_bus = event_bus
        self._positions: dict[str, Position] = {}
        self._next_id = 1
        event_bus.subscribe(OrderFilled, self._on_filled)

    def get_position(self, symbol: Symbol) -> Position | None:
        return self._positions.get(symbol.canonical)

    def list_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def _on_filled(self, event: OrderFilled) -> None:
        order = self._order_manager.get_order(event.ack.correlation_id)
        if order is None:
            raise KeyError(f"Unknown order '{event.ack.correlation_id}' for fill")
        await self._apply_fill(order.request, event.ack)

    def _next_position_id(self) -> str:
        position_id = str(self._next_id)
        self._next_id += 1
        return position_id

    async def _apply_fill(self, request: OrderRequest, ack: OrderAck) -> None:
        if ack.fill_price is None:
            raise ValueError(f"Fill for '{request.correlation_id}' has no fill_price")
        fill_price = ack.fill_price
        key = request.symbol.canonical
        existing = self._positions.get(key)

        if existing is None:
            self._positions[key] = Position(
                position_id=self._next_position_id(),
                symbol=request.symbol,
                side=request.side,
                volume=request.volume,
                open_price=fill_price,
            )
            return

        if existing.side == request.side:
            total_volume = existing.volume + request.volume
            weighted_price = (
                existing.open_price * existing.volume + fill_price * request.volume
            ) / total_volume
            self._positions[key] = Position(
                position_id=existing.position_id,
                symbol=existing.symbol,
                side=existing.side,
                volume=total_volume,
                open_price=weighted_price,
                stop_loss=existing.stop_loss,
                take_profit=existing.take_profit,
            )
            return

        # Opposite side: reduces, exactly closes, or closes-and-reverses.
        if request.volume < existing.volume:
            self._positions[key] = Position(
                position_id=existing.position_id,
                symbol=existing.symbol,
                side=existing.side,
                volume=existing.volume - request.volume,
                open_price=existing.open_price,
                stop_loss=existing.stop_loss,
                take_profit=existing.take_profit,
            )
            return

        del self._positions[key]
        await self._event_bus.publish(PositionClosed(position=existing))

        if request.volume > existing.volume:
            remainder = request.volume - existing.volume
            self._positions[key] = Position(
                position_id=self._next_position_id(),
                symbol=request.symbol,
                side=request.side,
                volume=remainder,
                open_price=fill_price,
            )


__all__ = ["PositionManager"]
