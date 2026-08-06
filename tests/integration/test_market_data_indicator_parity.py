from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from core.event_bus.bus import EventBus
from core.indicators.momentum import RelativeStrengthIndex
from core.indicators.trend import SimpleMovingAverage
from core.interfaces.events import BarClosed
from core.interfaces.types import Bar, Symbol, Timeframe
from core.market_data.engine import MarketDataEngine
from core.market_data.fake_live import FakeLiveBarProvider
from core.market_data.replay import ParquetBarReplayProvider

_SYMBOL = Symbol(name="EURUSD")
_TIMEFRAME = Timeframe.M1
_CLOSES = [1.1000, 1.1010, 1.0995, 1.1020, 1.1030, 1.1015, 1.1040, 1.1055]


def _bars() -> list[Bar]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=_TIMEFRAME,
            timestamp=start + timedelta(minutes=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=100.0,
        )
        for i, close in enumerate(_CLOSES)
    ]


def _write_parquet(bars: list[Bar], path: Path) -> None:
    table = pa.table(
        {
            "symbol": [bar.symbol.canonical for bar in bars],
            "timeframe": [bar.timeframe.value for bar in bars],
            "timestamp": [bar.timestamp for bar in bars],
            "open": [bar.open for bar in bars],
            "high": [bar.high for bar in bars],
            "low": [bar.low for bar in bars],
            "close": [bar.close for bar in bars],
            "volume": [bar.volume for bar in bars],
        }
    )
    pq.write_table(table, path)


async def _run_and_collect_indicator_series(
    provider: ParquetBarReplayProvider | FakeLiveBarProvider,
) -> tuple[list[float | None], list[float | None]]:
    event_bus = EventBus()
    engine = MarketDataEngine(provider, event_bus)

    sma = SimpleMovingAverage(period=3)
    rsi = RelativeStrengthIndex(period=3)
    sma_series: list[float | None] = []
    rsi_series: list[float | None] = []

    async def on_bar(event: BarClosed) -> None:
        sma_series.append(sma.update(event.bar))
        rsi_series.append(rsi.update(event.bar))

    event_bus.subscribe(BarClosed, on_bar)
    await engine.run_bars(_SYMBOL, _TIMEFRAME)

    return sma_series, rsi_series


@pytest.mark.asyncio
async def test_replay_and_fake_live_produce_identical_indicator_output(tmp_path: Path) -> None:
    bars = _bars()
    parquet_path = tmp_path / "eurusd_m1.parquet"
    _write_parquet(bars, parquet_path)

    replay_provider = ParquetBarReplayProvider(parquet_path)
    fake_live_provider = FakeLiveBarProvider(bars)

    replay_sma, replay_rsi = await _run_and_collect_indicator_series(replay_provider)
    live_sma, live_rsi = await _run_and_collect_indicator_series(fake_live_provider)

    assert replay_sma == live_sma
    assert replay_rsi == live_rsi
    # Sanity: the engine actually warmed up and produced real values, not all-None.
    assert any(value is not None for value in replay_sma)
    assert any(value is not None for value in replay_rsi)
