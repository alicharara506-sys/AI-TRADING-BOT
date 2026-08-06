from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from core.interfaces.types import Bar, Symbol, Tick, Timeframe


@runtime_checkable
class DataProvider(Protocol):
    def stream_ticks(self, symbol: Symbol) -> AsyncIterator[Tick]: ...

    def stream_bars(self, symbol: Symbol, timeframe: Timeframe) -> AsyncIterator[Bar]: ...
