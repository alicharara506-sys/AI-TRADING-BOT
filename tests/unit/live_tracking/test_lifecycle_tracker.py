from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.event_bus.bus import EventBus
from core.interfaces.events import TickReceived
from core.interfaces.types import Direction, Evidence, Symbol, Tick, TradeSignal
from database.repository import SqliteSignalRepository
from decision_engine.report import DecisionReport
from live_tracking.events import (
    SignalExpired,
    SignalOutcomeOpened,
    SignalTriggered,
    StopLossHit,
    TakeProfitHit,
)
from live_tracking.lifecycle_tracker import SignalLifecycleTracker
from live_tracking.types import OutcomeStatus

_SYMBOL = Symbol(name="XAUUSD")
_START = datetime(2026, 1, 1, tzinfo=UTC)


_TrackerFixture = tuple[SignalLifecycleTracker, EventBus, SqliteSignalRepository]


def _tracker(*, id_factory: object = None) -> _TrackerFixture:
    bus = EventBus()
    repository = SqliteSignalRepository("sqlite:///:memory:")
    kwargs = {"id_factory": id_factory} if id_factory is not None else {}
    tracker = SignalLifecycleTracker(bus, repository, **kwargs)  # type: ignore[arg-type]
    return tracker, bus, repository


def _report(
    *, take_profit_2: float | None = 4387.20, direction: Direction = Direction.LONG
) -> DecisionReport:
    signal = TradeSignal(
        symbol=_SYMBOL,
        direction=direction,
        combined_confidence=0.66,
        threshold=0.5,
        evidence=(Evidence(source_module="adx_trend", direction=direction, confidence=0.7),),
    )
    stop_loss = 4327.20 if direction is Direction.LONG else 4369.34
    take_profit = 4368.00 if direction is Direction.LONG else 4328.54
    tp2 = take_profit_2
    return DecisionReport(
        signal=signal,
        confidence=0.66,
        probability_of_success=0.66,
        recommended_position_size=0.01,
        recommended_stop_loss=stop_loss,
        recommended_take_profit=take_profit,
        uncertainty="medium",
        atr=4.5,
        take_profit_2=tp2,
    )


def _tick(
    price: float, *, at: datetime = _START, symbol: Symbol = _SYMBOL, ask: float | None = None
) -> TickReceived:
    return TickReceived(
        Tick(symbol=symbol, timestamp=at, bid=price, ask=ask if ask is not None else price)
    )


@pytest.mark.asyncio
async def test_track_opens_an_active_outcome_and_publishes_event() -> None:
    tracker, bus, repository = _tracker(id_factory=lambda: "o1")
    received: list[SignalOutcomeOpened] = []
    bus.subscribe(SignalOutcomeOpened, received.append)

    outcome = await tracker.track(
        _report(),
        strategy_name="signal_fusion",
        entry_price=4348.27,
        pip_size=0.1,
        now=_START,
    )

    assert outcome.status is OutcomeStatus.ACTIVE
    assert outcome.id == "o1"
    assert repository.get_outcome("o1") is not None
    assert len(received) == 1 and received[0].outcome_id == "o1"


@pytest.mark.asyncio
async def test_track_rejects_a_report_without_stop_and_target() -> None:
    tracker, _bus, _repo = _tracker()
    incomplete = DecisionReport(
        signal=TradeSignal(
            symbol=_SYMBOL,
            direction=Direction.LONG,
            combined_confidence=0.5,
            threshold=0.5,
            evidence=(),
        ),
        confidence=0.5,
        probability_of_success=0.5,
        recommended_position_size=0.0,
        recommended_stop_loss=None,
        recommended_take_profit=None,
        uncertainty="high",
        atr=None,
    )
    with pytest.raises(ValueError):
        await tracker.track(incomplete, strategy_name="s", entry_price=1.0, pip_size=0.1)


@pytest.mark.asyncio
async def test_tp1_hit_is_not_terminal_when_tp2_is_configured() -> None:
    tracker, bus, repository = _tracker(id_factory=lambda: "o1")
    tp1_events: list[TakeProfitHit] = []
    bus.subscribe(TakeProfitHit, tp1_events.append)
    await tracker.track(_report(), strategy_name="s", entry_price=4348.27, pip_size=0.1, now=_START)

    await bus.publish(_tick(4368.05))

    assert len(tp1_events) == 1
    assert tp1_events[0].target.value == "TP1"
    assert len(tracker.open_outcomes()) == 1
    assert tracker.open_outcomes()[0].status is OutcomeStatus.TP1_HIT
    row = repository.get_outcome("o1")
    assert row is not None and row.status == "tp1_hit" and row.timestamp_resolved is None


@pytest.mark.asyncio
async def test_final_target_hit_resolves_the_outcome() -> None:
    tracker, bus, repository = _tracker(id_factory=lambda: "o1")
    tp_events: list[TakeProfitHit] = []
    bus.subscribe(TakeProfitHit, tp_events.append)
    await tracker.track(_report(), strategy_name="s", entry_price=4348.27, pip_size=0.1, now=_START)

    await bus.publish(_tick(4368.05))
    await bus.publish(_tick(4387.25))

    assert [e.target.value for e in tp_events] == ["TP1", "TP2"]
    assert tracker.open_outcomes() == []
    row = repository.get_outcome("o1")
    assert row is not None
    assert row.status == "tp2_hit"
    assert row.timestamp_resolved is not None
    assert row.final_pips == pytest.approx(390.0, abs=0.5)
    assert row.achieved_risk_reward is not None and row.achieved_risk_reward > 0


@pytest.mark.asyncio
async def test_sl_hit_resolves_with_negative_pips() -> None:
    tracker, bus, repository = _tracker(id_factory=lambda: "o1")
    sl_events: list[StopLossHit] = []
    bus.subscribe(StopLossHit, sl_events.append)
    await tracker.track(_report(), strategy_name="s", entry_price=4348.27, pip_size=0.1, now=_START)

    await bus.publish(_tick(4327.10))

    assert len(sl_events) == 1
    assert sl_events[0].pips < 0
    row = repository.get_outcome("o1")
    assert row is not None and row.status == "sl_hit" and row.timestamp_resolved is not None
    assert row.achieved_risk_reward == pytest.approx(-1.0, abs=0.05)


@pytest.mark.asyncio
async def test_short_direction_hits_are_mirrored() -> None:
    tracker, bus, repository = _tracker(id_factory=lambda: "o1")
    await tracker.track(
        _report(direction=Direction.SHORT, take_profit_2=None),
        strategy_name="s",
        entry_price=4348.27,
        pip_size=0.1,
        now=_START,
    )

    await bus.publish(_tick(4328.50))

    row = repository.get_outcome("o1")
    assert row is not None
    assert row.status == "tp1_hit"
    assert row.timestamp_resolved is not None
    assert row.final_pips is not None and row.final_pips > 0


@pytest.mark.asyncio
async def test_pending_signal_triggers_then_tracks_normally() -> None:
    tracker, bus, repository = _tracker(id_factory=lambda: "o1")
    triggered: list[SignalTriggered] = []
    bus.subscribe(SignalTriggered, triggered.append)
    await tracker.track(
        _report(),
        strategy_name="s",
        entry_price=4348.27,
        pip_size=0.1,
        trigger_price=4350.00,
        now=_START,
    )
    assert tracker.open_outcomes()[0].status is OutcomeStatus.PENDING

    await bus.publish(_tick(4349.90, ask=4350.10))

    assert len(triggered) == 1
    assert tracker.open_outcomes()[0].status is OutcomeStatus.ACTIVE
    row = repository.get_outcome("o1")
    assert row is not None and row.status == "active" and row.timestamp_triggered is not None


@pytest.mark.asyncio
async def test_pending_signal_expires_after_four_hours_without_triggering() -> None:
    tracker, bus, repository = _tracker(id_factory=lambda: "o1")
    expired: list[SignalExpired] = []
    bus.subscribe(SignalExpired, expired.append)
    await tracker.track(
        _report(),
        strategy_name="s",
        entry_price=4348.27,
        pip_size=0.1,
        trigger_price=4400.00,
        now=_START,
    )

    later = _START + timedelta(hours=4, minutes=1)
    await bus.publish(TickReceived(Tick(symbol=_SYMBOL, timestamp=later, bid=4349.0, ask=4349.2)))

    assert len(expired) == 1
    assert tracker.open_outcomes() == []
    row = repository.get_outcome("o1")
    assert row is not None and row.status == "expired"


@pytest.mark.asyncio
async def test_ticks_for_other_symbols_are_ignored() -> None:
    tracker, bus, repository = _tracker(id_factory=lambda: "o1")
    await tracker.track(_report(), strategy_name="s", entry_price=4348.27, pip_size=0.1, now=_START)
    other_symbol = Symbol(name="EURUSD")

    await bus.publish(_tick(1.0, symbol=other_symbol))

    assert tracker.open_outcomes()[0].status is OutcomeStatus.ACTIVE


@pytest.mark.asyncio
async def test_close_manual_resolves_without_a_target() -> None:
    tracker, _bus, repository = _tracker(id_factory=lambda: "o1")
    await tracker.track(_report(), strategy_name="s", entry_price=4348.27, pip_size=0.1, now=_START)

    await tracker.close_manual("o1", price=4355.0, at=_START + timedelta(minutes=10))

    assert tracker.open_outcomes() == []
    row = repository.get_outcome("o1")
    assert row is not None and row.status == "closed_manual" and row.hit_target is None


@pytest.mark.asyncio
async def test_close_manual_raises_for_unknown_outcome() -> None:
    tracker, _bus, _repo = _tracker()
    with pytest.raises(ValueError):
        await tracker.close_manual("missing", price=1.0)


@pytest.mark.asyncio
async def test_live_price_samples_are_throttled_by_sample_interval() -> None:
    bus = EventBus()
    repository = SqliteSignalRepository("sqlite:///:memory:")
    tracker = SignalLifecycleTracker(
        bus, repository, sample_interval=timedelta(seconds=5), id_factory=lambda: "o1"
    )
    await tracker.track(_report(), strategy_name="s", entry_price=4348.27, pip_size=0.1, now=_START)

    for offset in (0, 1, 2, 6, 7, 12):
        await bus.publish(
            TickReceived(
                Tick(
                    symbol=_SYMBOL,
                    timestamp=_START + timedelta(seconds=offset),
                    bid=4350.0,
                    ask=4350.0,
                )
            )
        )

    samples = repository.list_outcome_samples("o1")
    assert len(samples) == 3
