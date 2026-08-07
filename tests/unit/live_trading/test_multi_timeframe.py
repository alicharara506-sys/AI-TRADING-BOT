from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Symbol, Timeframe
from live_trading.multi_timeframe import fetch_multi_timeframe_bars

_SYMBOL = Symbol(name="EURUSD")


def _bars(timeframe: Timeframe, count: int) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=timeframe,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=1.10,
            high=1.10,
            low=1.10,
            close=1.10,
            volume=1.0,
        )
        for i in range(count)
    ]


class _FakeHistoricalBarSource:
    def __init__(self) -> None:
        self.calls: list[tuple[Symbol, Timeframe, int]] = []

    async def get_historical_bars(
        self, symbol: Symbol, timeframe: Timeframe, count: int
    ) -> list[Bar]:
        self.calls.append((symbol, timeframe, count))
        return _bars(timeframe, count)


async def test_fetches_bars_for_every_requested_timeframe() -> None:
    connector = _FakeHistoricalBarSource()

    result = await fetch_multi_timeframe_bars(
        connector, _SYMBOL, [Timeframe.H1, Timeframe.H4, Timeframe.D1], count=10
    )

    assert set(result) == {Timeframe.H1, Timeframe.H4, Timeframe.D1}
    assert len(result[Timeframe.H1]) == 10
    assert all(bar.timeframe == Timeframe.H4 for bar in result[Timeframe.H4])


async def test_calls_the_connector_once_per_timeframe_with_the_requested_count() -> None:
    connector = _FakeHistoricalBarSource()

    await fetch_multi_timeframe_bars(connector, _SYMBOL, [Timeframe.H1, Timeframe.H4], count=25)

    assert connector.calls == [
        (_SYMBOL, Timeframe.H1, 25),
        (_SYMBOL, Timeframe.H4, 25),
    ]


async def test_returns_an_empty_dict_for_an_empty_timeframe_list() -> None:
    connector = _FakeHistoricalBarSource()

    result = await fetch_multi_timeframe_bars(connector, _SYMBOL, [], count=10)

    assert result == {}


async def test_rejects_an_invalid_count() -> None:
    connector = _FakeHistoricalBarSource()

    with pytest.raises(ValueError):
        await fetch_multi_timeframe_bars(connector, _SYMBOL, [Timeframe.H1], count=0)
