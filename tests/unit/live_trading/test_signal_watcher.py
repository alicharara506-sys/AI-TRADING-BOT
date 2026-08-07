from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


def _bar(symbol: Symbol = _SYMBOL, *, index: int = 0) -> Bar:
    return Bar(
        symbol=symbol,
        timeframe=Timeframe.M15,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * index),
        open=1.10,
        high=1.10,
        low=1.10,
        close=1.10,
        volume=0.0,
    )


@pytest.mark.asyncio
async def test_calls_on_signal_when_strategy_emits_a_signal() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar, tuple[Bar, ...]]] = []
    SignalWatcher(
        _SYMBOL,
        _AlwaysLongStrategy(),
        event_bus,
        on_signal=lambda s, b, h: calls.append((s, b, h)),
    )

    await event_bus.publish(BarClosed(bar=_bar()))

    assert len(calls) == 1
    signal, bar, history = calls[0]
    assert signal.direction is Direction.LONG
    assert bar.symbol == _SYMBOL
    assert history == (bar,)


@pytest.mark.asyncio
async def test_ignores_bars_for_a_different_symbol() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar, tuple[Bar, ...]]] = []
    SignalWatcher(
        _SYMBOL,
        _AlwaysLongStrategy(),
        event_bus,
        on_signal=lambda s, b, h: calls.append((s, b, h)),
    )

    await event_bus.publish(BarClosed(bar=_bar(symbol=_OTHER_SYMBOL)))

    assert calls == []


@pytest.mark.asyncio
async def test_does_not_call_on_signal_when_strategy_returns_none() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar, tuple[Bar, ...]]] = []
    SignalWatcher(
        _SYMBOL,
        _NeverSignalsStrategy(),
        event_bus,
        on_signal=lambda s, b, h: calls.append((s, b, h)),
    )

    await event_bus.publish(BarClosed(bar=_bar()))

    assert calls == []


@pytest.mark.asyncio
async def test_history_is_seeded_and_grows_with_new_bars() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar, tuple[Bar, ...]]] = []
    seed = (_bar(index=0), _bar(index=1))
    SignalWatcher(
        _SYMBOL,
        _AlwaysLongStrategy(),
        event_bus,
        on_signal=lambda s, b, h: calls.append((s, b, h)),
        history=seed,
    )

    new_bar = _bar(index=2)
    await event_bus.publish(BarClosed(bar=new_bar))

    assert calls[0][2] == (*seed, new_bar)


@pytest.mark.asyncio
async def test_history_ignores_seeded_bars_for_a_different_symbol() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar, tuple[Bar, ...]]] = []
    seed = (_bar(symbol=_OTHER_SYMBOL, index=0), _bar(index=1))
    SignalWatcher(
        _SYMBOL,
        _AlwaysLongStrategy(),
        event_bus,
        on_signal=lambda s, b, h: calls.append((s, b, h)),
        history=seed,
    )

    new_bar = _bar(index=2)
    await event_bus.publish(BarClosed(bar=new_bar))

    assert calls[0][2] == (seed[1], new_bar)


@pytest.mark.asyncio
async def test_history_is_bounded_by_max_history() -> None:
    event_bus = EventBus()
    calls: list[tuple[TradeSignal, Bar, tuple[Bar, ...]]] = []
    seed = tuple(_bar(index=i) for i in range(3))
    SignalWatcher(
        _SYMBOL,
        _AlwaysLongStrategy(),
        event_bus,
        on_signal=lambda s, b, h: calls.append((s, b, h)),
        history=seed,
        max_history=2,
    )

    new_bar = _bar(index=3)
    await event_bus.publish(BarClosed(bar=new_bar))

    assert len(calls[0][2]) == 2
    assert calls[0][2] == (seed[-1], new_bar)
