from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.event_bus.bus import EventBus
from core.interfaces.events import AccountStateChanged, BarClosed
from core.interfaces.risk import RiskModel
from core.interfaces.strategy import Strategy
from core.interfaces.types import (
    AccountState,
    Bar,
    Direction,
    Evidence,
    OrderAck,
    OrderRequest,
    OrderStatus,
    Symbol,
    Timeframe,
    TradeSignal,
)
from core.strategy.engine import StrategyEngine

_SYMBOL = Symbol(name="EURUSD")


def _bar(close: float = 1.1) -> Bar:
    return Bar(
        symbol=_SYMBOL,
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0,
    )


def _account_state(equity: float = 10_000.0) -> AccountState:
    return AccountState(
        balance=equity, equity=equity, margin=0.0, free_margin=equity,
        margin_level=None, currency="USD",
    )


def _signal(direction: Direction) -> TradeSignal:
    return TradeSignal(
        symbol=_SYMBOL,
        direction=direction,
        combined_confidence=1.0,
        threshold=0.0,
        evidence=(Evidence(source_module="test", direction=direction, confidence=1.0),),
    )


class _AlwaysApproveRiskModel:
    def evaluate_signal(self, signal: TradeSignal) -> TradeSignal | None:
        return signal

    def evaluate_order(self, request: OrderRequest) -> OrderRequest | None:
        return request


class _AlwaysVetoRiskModel:
    def evaluate_signal(self, signal: TradeSignal) -> TradeSignal | None:
        return None

    def evaluate_order(self, request: OrderRequest) -> OrderRequest | None:
        return None


class _FixedVolume:
    def __init__(self, volume: float) -> None:
        self._volume = volume

    def size(self, signal: TradeSignal, *, equity: float) -> float:
        return self._volume


class _RecordingExecutionEngine:
    def __init__(self) -> None:
        self.submitted: list[OrderRequest] = []

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        self.submitted.append(request)
        return OrderAck(
            correlation_id=request.correlation_id,
            broker_order_id="recorded",
            status=OrderStatus.FILLED,
            fill_price=1.0,
        )

    async def cancel_order(self, correlation_id: str) -> None:
        return None


class _ScriptedStrategy:
    """Returns each queued signal in order, one per on_bar call, then None."""

    strategy_name = "scripted"

    def __init__(self, signals: list[TradeSignal | None]) -> None:
        self._signals = list(signals)

    def on_bar(self, bar: Bar) -> TradeSignal | None:
        if not self._signals:
            return None
        return self._signals.pop(0)


def _make_engine(
    event_bus: EventBus,
    strategy: Strategy,
    execution_engine: _RecordingExecutionEngine,
    *,
    risk_model: RiskModel | None = None,
    volume: float = 0.1,
) -> StrategyEngine:
    return StrategyEngine(
        strategy,
        risk_model or _AlwaysApproveRiskModel(),
        _FixedVolume(volume),
        execution_engine,
        event_bus,
    )


@pytest.mark.asyncio
async def test_no_trade_before_equity_snapshot_exists() -> None:
    event_bus = EventBus()
    strategy = _ScriptedStrategy([_signal(Direction.LONG)])
    execution_engine = _RecordingExecutionEngine()
    _make_engine(event_bus, strategy, execution_engine)

    await event_bus.publish(BarClosed(bar=_bar()))

    assert execution_engine.submitted == []


@pytest.mark.asyncio
async def test_long_signal_submits_buy_order_after_equity_known() -> None:
    event_bus = EventBus()
    strategy = _ScriptedStrategy([_signal(Direction.LONG)])
    execution_engine = _RecordingExecutionEngine()
    _make_engine(event_bus, strategy, execution_engine, volume=0.2)

    await event_bus.publish(AccountStateChanged(account_state=_account_state()))
    await event_bus.publish(BarClosed(bar=_bar()))

    assert len(execution_engine.submitted) == 1


@pytest.mark.asyncio
async def test_vetoed_signal_never_reaches_execution_engine() -> None:
    event_bus = EventBus()
    strategy = _ScriptedStrategy([_signal(Direction.LONG)])
    execution_engine = _RecordingExecutionEngine()
    _make_engine(event_bus, strategy, execution_engine, risk_model=_AlwaysVetoRiskModel())

    await event_bus.publish(AccountStateChanged(account_state=_account_state()))
    await event_bus.publish(BarClosed(bar=_bar()))

    assert execution_engine.submitted == []


@pytest.mark.asyncio
async def test_neutral_direction_does_not_submit_an_order() -> None:
    event_bus = EventBus()
    strategy = _ScriptedStrategy([_signal(Direction.NEUTRAL)])
    execution_engine = _RecordingExecutionEngine()
    _make_engine(event_bus, strategy, execution_engine)

    await event_bus.publish(AccountStateChanged(account_state=_account_state()))
    await event_bus.publish(BarClosed(bar=_bar()))

    assert execution_engine.submitted == []


@pytest.mark.asyncio
async def test_non_positive_sizing_does_not_submit_an_order() -> None:
    event_bus = EventBus()
    strategy = _ScriptedStrategy([_signal(Direction.LONG)])
    execution_engine = _RecordingExecutionEngine()
    _make_engine(event_bus, strategy, execution_engine, volume=0.0)

    await event_bus.publish(AccountStateChanged(account_state=_account_state()))
    await event_bus.publish(BarClosed(bar=_bar()))

    assert execution_engine.submitted == []


@pytest.mark.asyncio
async def test_hot_swap_strategy_takes_effect_on_next_bar_without_resubscribing() -> None:
    event_bus = EventBus()
    quiet_strategy = _ScriptedStrategy([None])
    execution_engine = _RecordingExecutionEngine()
    engine = _make_engine(event_bus, quiet_strategy, execution_engine)
    await event_bus.publish(AccountStateChanged(account_state=_account_state()))

    await event_bus.publish(BarClosed(bar=_bar()))
    assert execution_engine.submitted == []

    engine.set_strategy(_ScriptedStrategy([_signal(Direction.SHORT)]))
    await event_bus.publish(BarClosed(bar=_bar()))

    assert len(execution_engine.submitted) == 1


@pytest.mark.asyncio
async def test_order_submitted_carries_a_unique_correlation_id_per_signal() -> None:
    event_bus = EventBus()
    strategy = _ScriptedStrategy([_signal(Direction.LONG), _signal(Direction.SHORT)])
    execution_engine = _RecordingExecutionEngine()
    _make_engine(event_bus, strategy, execution_engine)
    await event_bus.publish(AccountStateChanged(account_state=_account_state()))

    await event_bus.publish(BarClosed(bar=_bar()))
    await event_bus.publish(BarClosed(bar=_bar()))

    ids = {request.correlation_id for request in execution_engine.submitted}
    assert len(ids) == 2
