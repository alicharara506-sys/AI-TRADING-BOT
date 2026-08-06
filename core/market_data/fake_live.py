from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from core.interfaces.types import Bar, Symbol, Tick, Timeframe


class FakeLiveBarProvider:
    """Stands in for a real MT4/MT5 tick-forwarded live feed in tests: same
    DataProvider contract as ParquetBarReplayProvider, backed by an in-memory
    sequence instead of a file, with no simulated network delay.
    """

    def __init__(self, bars: Sequence[Bar]) -> None:
        self._bars = list(bars)

    async def stream_ticks(self, symbol: Symbol) -> AsyncIterator[Tick]:
        raise NotImplementedError("FakeLiveBarProvider serves bars only")
        yield  # pragma: no cover - unreachable; required so this stays a generator

    async def stream_bars(self, symbol: Symbol, timeframe: Timeframe) -> AsyncIterator[Bar]:
        for bar in self._bars:
            if bar.symbol.canonical == symbol.canonical and bar.timeframe == timeframe:
                yield bar


__all__ = ["FakeLiveBarProvider"]
