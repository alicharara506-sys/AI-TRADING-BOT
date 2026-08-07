from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.event_bus.bus import EventBus
from core.interfaces.events import BarClosed
from core.interfaces.types import Bar, Direction, Evidence, Symbol, Timeframe, TradeSignal
from live_trading.signal_watcher import SignalWatcher

_SYMBOL = Symbol(name="EURUSD")
_OTHER_SYMBOL = Symbol(name="GBPUSD")


class _AlwaysLongStrategy:
    strategy_name = "always_long"

    def on_bar(self, bar: Bar) -> TradeSignal | None:
        evidence = Evidence(
            source_module=self.strategy_name, direction=Direction.LONG, confidence=1.0
        )
        return TradeSignal(
            symbol=bar.symbol,
            direction=Direction.LONG,
            combined_confidence=1.0,
            threshold=0.0,
            evidence=(evidence,),
        )


class _NeverSignalsStrategy:
    strategy_name = "never_signals"

    def on_bar(self, bar: Bar) -> TradeSignal | None:
        return None


def _bar(symbol: Symbol = _SYMBOL) -> Bar:
    return Bar(
        symbol=symbol,
        timeframe=Timeframe.M15,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=1.10,
        high=1.10,
        low=1.10,
        close=1.10,
        volume=0.0,
    )


@pytest.mark.asyncio
async def test_calls_on_signal_when_strategy_emits_a_signal() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar]] = []
    SignalWatcher(
        _SYMBOL, _AlwaysLongStrategy(), event_bus, on_signal=lambda s, b: calls.append((s, b))
    )

    await event_bus.publish(BarClosed(bar=_bar()))

    assert len(calls) == 1
    signal, bar = calls[0]
    assert signal.direction is Direction.LONG
    assert bar.symbol == _SYMBOL


@pytest.mark.asyncio
async def test_ignores_bars_for_a_different_symbol() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar]] = []
    SignalWatcher(
        _SYMBOL, _AlwaysLongStrategy(), event_bus, on_signal=lambda s, b: calls.append((s, b))
    )

    await event_bus.publish(BarClosed(bar=_bar(symbol=_OTHER_SYMBOL)))

    assert calls == []


@pytest.mark.asyncio
async def test_does_not_call_on_signal_when_strategy_returns_none() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar]] = []
    SignalWatcher(
        _SYMBOL, _NeverSignalsStrategy(), event_bus, on_signal=lambda s, b: calls.append((s, b))
    )

    await event_bus.publish(BarClosed(bar=_bar()))

    assert calls == []
