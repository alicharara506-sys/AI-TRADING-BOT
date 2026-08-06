from __future__ import annotations

from core.interfaces.types import OrderSide, Position, Symbol
from core.portfolio.position_manager import PositionManager


class PortfolioEngine:
    """Read-side (CQRS query) aggregation over the Position Manager: exposure and
    position-count queries used by the Risk Engine and, later, analytics/
    reporting. Position Manager remains the only mutator -- this engine never
    writes position state.
    """

    def __init__(self, position_manager: PositionManager) -> None:
        self._position_manager = position_manager

    def get_position(self, symbol: Symbol) -> Position | None:
        return self._position_manager.get_position(symbol)

    def list_positions(self) -> list[Position]:
        return self._position_manager.list_positions()

    def signed_exposure(self, symbol: Symbol) -> float:
        position = self.get_position(symbol)
        if position is None:
            return 0.0
        return position.volume if position.side is OrderSide.BUY else -position.volume

    def total_exposure(self) -> float:
        return sum(position.volume for position in self.list_positions())

    def open_position_count(self) -> int:
        return len(self.list_positions())


__all__ = ["PortfolioEngine"]
