from __future__ import annotations

from core.interfaces.connector import Connector
from core.interfaces.execution import ExecutionEngine
from core.interfaces.types import OrderAck, OrderRequest, OrderSide


class FlipSafeExecutionEngine:
    """Closes any existing opposite-side position for the requested symbol
    before submitting a new order.

    Why this exists: an MT5 hedging account -- AccountMode.HEDGING, the mode
    this platform's own connectivity check found on a real SupremeFX-Server
    demo account -- does not net an opposite-side market order against an
    existing position the way the kernel's own simulated PositionManager
    does; it opens a second, independent position alongside it. A strategy
    like SmaCrossoverStrategy that "flips" direction with a same-volume
    opposite order would silently end up holding both a long and a short at
    once on a real hedging account without this wrapper.

    Position state is read fresh from the connector on every call, not from
    the kernel's own PositionManager: that ledger only observes fills
    published through submit_order(), so it never sees the close_position()
    calls made here directly and would drift from broker reality if trusted
    for this decision. It remains correct for RiskEngine's own
    max_open_positions *count* check even so, since this wrapper's closes
    happen in addition to, not instead of, the normal fill flow for the new
    order that follows.
    """

    def __init__(self, connector: Connector, inner: ExecutionEngine) -> None:
        self._connector = connector
        self._inner = inner

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        opposite_side = OrderSide.SELL if request.side is OrderSide.BUY else OrderSide.BUY
        positions = await self._connector.get_open_positions()
        for position in positions:
            if (
                position.symbol.canonical == request.symbol.canonical
                and position.side is opposite_side
            ):
                await self._connector.close_position(position.position_id)
        return await self._inner.submit_order(request)

    async def cancel_order(self, correlation_id: str) -> None:
        await self._inner.cancel_order(correlation_id)


__all__ = ["FlipSafeExecutionEngine"]
