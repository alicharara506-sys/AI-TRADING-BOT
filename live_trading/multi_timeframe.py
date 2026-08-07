"""Multi-timeframe bar fetching: populates
core.interfaces.types.MarketContext.higher_timeframe_bars from a real (or
fake, in tests) connector, for callers that want
quant.multi_timeframe.alignment.HigherTimeframeAlignmentModule (or any
future multi-timeframe module) to have real higher-timeframe data to vote
on. Deliberately not wired into LiveRunner/SignalWatcher/run_dashboard_feed.py
yet -- this is the fetch primitive those call sites would use, not a
rewrite of any of them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from core.interfaces.types import Bar, Symbol, Timeframe


@runtime_checkable
class HistoricalBarSource(Protocol):
    async def get_historical_bars(
        self, symbol: Symbol, timeframe: Timeframe, count: int
    ) -> list[Bar]: ...


async def fetch_multi_timeframe_bars(
    connector: HistoricalBarSource,
    symbol: Symbol,
    timeframes: Sequence[Timeframe],
    *,
    count: int,
) -> dict[Timeframe, tuple[Bar, ...]]:
    """Fetches `count` historical bars for each of `timeframes`, one
    get_historical_bars call per timeframe in sequence -- there's no
    batched multi-timeframe fetch in the underlying MT5 API to parallelize
    against, and running them concurrently would just interleave calls into
    the same non-reentrant IPC connection anyway.
    """
    if count < 1:
        raise ValueError("count must be >= 1")

    result: dict[Timeframe, tuple[Bar, ...]] = {}
    for timeframe in timeframes:
        bars = await connector.get_historical_bars(symbol, timeframe, count)
        result[timeframe] = tuple(bars)
    return result


__all__ = ["HistoricalBarSource", "fetch_multi_timeframe_bars"]
