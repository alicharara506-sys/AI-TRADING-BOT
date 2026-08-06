from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pyarrow.parquet as pq

from core.interfaces.types import Bar, Symbol, Tick, Timeframe


class ParquetBarReplayProvider:
    """Historical Bar source read from a Parquet file, replayed in timestamp order.

    Serves as the backtest-side counterpart to a live connector's bar stream: same
    DataProvider contract, so the Market Data Engine and everything downstream of it
    cannot tell historical replay apart from a live feed.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    async def stream_ticks(self, symbol: Symbol) -> AsyncIterator[Tick]:
        raise NotImplementedError("ParquetBarReplayProvider serves bars only")
        yield  # pragma: no cover - unreachable; required so this stays a generator

    async def stream_bars(self, symbol: Symbol, timeframe: Timeframe) -> AsyncIterator[Bar]:
        table = pq.read_table(self._path)
        rows = table.to_pylist()
        matching = [
            row
            for row in rows
            if row["symbol"] == symbol.canonical and row["timeframe"] == timeframe.value
        ]
        matching.sort(key=lambda row: row["timestamp"])
        for row in matching:
            yield Bar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=row["timestamp"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row.get("volume", 0.0),
            )


__all__ = ["ParquetBarReplayProvider"]
