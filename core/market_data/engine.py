from __future__ import annotations

from core.event_bus.bus import EventBus
from core.interfaces.data_provider import DataProvider
from core.interfaces.events import BarClosed, TickReceived
from core.interfaces.types import Symbol, Timeframe


class MarketDataEngine:
    """Drives a DataProvider and publishes canonical Tick/Bar events onto the bus.

    Downstream consumers (Indicator Engine, Strategy Engine, ...) see identical
    TickReceived/BarClosed events whether the provider is a historical replay or a
    live feed -- the engine itself never branches on the source.
    """

    def __init__(self, provider: DataProvider, event_bus: EventBus) -> None:
        self._provider = provider
        self._event_bus = event_bus

    async def run_ticks(self, symbol: Symbol) -> None:
        async for tick in self._provider.stream_ticks(symbol):
            await self._event_bus.publish(TickReceived(tick=tick))

    async def run_bars(self, symbol: Symbol, timeframe: Timeframe) -> None:
        async for bar in self._provider.stream_bars(symbol, timeframe):
            await self._event_bus.publish(BarClosed(bar=bar))


__all__ = ["MarketDataEngine"]
