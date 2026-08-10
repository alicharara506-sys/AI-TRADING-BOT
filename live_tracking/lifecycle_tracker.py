from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid4

from core.event_bus.bus import EventBus
from core.interfaces.events import TickReceived
from core.interfaces.types import Direction, Tick
from database.repository import SignalRepository
from decision_engine.report import DecisionReport
from live_tracking.events import (
    SignalExpired,
    SignalOutcomeOpened,
    SignalTriggered,
    StopLossHit,
    TakeProfitHit,
)
from live_tracking.types import HitTarget, LivePriceSample, OutcomeStatus, SignalOutcome

# status -> how many targets have already been hit (0 = none, i.e. ACTIVE).
# TP3_HIT never appears here: it is always terminal, so an outcome in that
# state is no longer in self._open and this tracker never re-evaluates it.
_LADDER_PROGRESS: dict[OutcomeStatus, int] = {
    OutcomeStatus.ACTIVE: 0,
    OutcomeStatus.TP1_HIT: 1,
    OutcomeStatus.TP2_HIT: 2,
}


def _crossed(direction: Direction, price: float, level: float, *, favorable: bool) -> bool:
    """Whether `price` has moved past `level` in the given sense: favorable
    means towards a take-profit (up for LONG, down for SHORT); not
    favorable means towards the stop-loss (the opposite side)."""
    moved_up = favorable if direction is Direction.LONG else not favorable
    return price >= level if moved_up else price <= level


class SignalLifecycleTracker:
    """Watches every DecisionReport handed to `track()` against live MT5
    ticks published on the shared EventBus (the same TickReceived event
    MT5Connector already publishes -- see connectors/mt5/connector.py) and
    records what actually happened: a PENDING conditional signal triggering,
    each configured take-profit target being reached in order, the
    stop-loss being hit, or a PENDING signal expiring before it ever
    triggered. Every state transition is persisted immediately via the
    injected SignalRepository, so a dashboard reading the same database
    sees live progress without holding its own EventBus subscription.

    Deliberately read-only with respect to the market: this platform's
    execution is a separate, explicit concern (ExecutionEngine); this class
    only ever *observes* whether pre-computed price levels were reached, it
    never places, modifies, or closes an order.
    """

    def __init__(
        self,
        event_bus: EventBus,
        repository: SignalRepository,
        *,
        expiry: timedelta = timedelta(hours=4),
        sample_interval: timedelta = timedelta(seconds=5),
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._event_bus = event_bus
        self._repository = repository
        self._expiry = expiry
        self._sample_interval = sample_interval
        self._id_factory = id_factory
        self._open: dict[str, SignalOutcome] = {}
        event_bus.subscribe(TickReceived, self._on_tick)

    def open_outcomes(self) -> list[SignalOutcome]:
        return list(self._open.values())

    async def track(
        self,
        report: DecisionReport,
        *,
        strategy_name: str,
        entry_price: float,
        pip_size: float,
        trigger_price: float | None = None,
        take_profit_3: float | None = None,
        regime: str | None = None,
        sentiment: float | None = None,
        ml_probability: float | None = None,
        now: datetime | None = None,
    ) -> SignalOutcome:
        """Starts tracking one DecisionReport. Raises if the report has no
        stop-loss/take-profit levels to track against -- a WAIT signal (no
        direction worth tracking) should never reach this method."""
        if report.recommended_stop_loss is None or report.recommended_take_profit is None:
            raise ValueError("cannot track a DecisionReport without stop-loss/take-profit levels")

        at = now if now is not None else datetime.utcnow()
        outcome = SignalOutcome(
            id=self._id_factory(),
            symbol=report.signal.symbol.canonical,
            direction=report.signal.direction,
            strategy_name=strategy_name,
            entry_price=entry_price,
            stop_loss=report.recommended_stop_loss,
            take_profit_1=report.recommended_take_profit,
            take_profit_2=report.take_profit_2,
            take_profit_3=take_profit_3,
            pip_size=pip_size,
            timestamp_generated=at,
            score_at_generation=report.confidence,
            uncertainty_at_generation=report.uncertainty,
            trigger_price=trigger_price,
            regime_at_generation=regime,
            sentiment_at_generation=sentiment,
            ml_probability_at_generation=ml_probability,
        )
        self._open[outcome.id] = outcome
        self._repository.save_outcome(outcome)
        await self._event_bus.publish(
            SignalOutcomeOpened(
                outcome_id=outcome.id, symbol=outcome.symbol, direction=outcome.direction, at=at
            )
        )
        return outcome

    async def close_manual(
        self, outcome_id: str, *, price: float, at: datetime | None = None
    ) -> SignalOutcome:
        """Ends tracking early at the dashboard user's request (the CLOSE
        button), independent of any target/stop level -- the resolved
        outcome is scored at whatever pips `price` implies right now."""
        outcome = self._open.get(outcome_id)
        if outcome is None:
            raise ValueError(f"'{outcome_id}' is not an open tracked outcome")
        self._resolve(outcome, None, price, at or datetime.utcnow(), OutcomeStatus.CLOSED_MANUAL)
        return outcome

    async def _on_tick(self, event: TickReceived) -> None:
        tick = event.tick
        symbol = tick.symbol.canonical
        # list(...) snapshot: _process_tick can remove the outcome from
        # self._open mid-iteration when it resolves.
        for outcome in list(self._open.values()):
            if outcome.symbol == symbol:
                await self._process_tick(outcome, tick)

    async def _process_tick(self, outcome: SignalOutcome, tick: Tick) -> None:
        if outcome.status is OutcomeStatus.PENDING:
            await self._process_pending(outcome, tick)
            return

        # A long position closes at the bid, a short at the ask -- the
        # conservative, realistic side of the spread for marking whether a
        # level has actually been reached.
        mark_price = tick.bid if outcome.direction is Direction.LONG else tick.ask
        pips = outcome.pips(mark_price)
        outcome.highest_pips = max(outcome.highest_pips, pips)
        outcome.lowest_pips = min(outcome.lowest_pips, pips)
        self._sample_if_due(outcome, mark_price, tick.timestamp)

        if _crossed(outcome.direction, mark_price, outcome.stop_loss, favorable=False):
            self._resolve(outcome, HitTarget.SL, mark_price, tick.timestamp, OutcomeStatus.SL_HIT)
            await self._event_bus.publish(
                StopLossHit(
                    outcome_id=outcome.id,
                    symbol=outcome.symbol,
                    price=mark_price,
                    pips=outcome.final_pips or 0.0,
                    at=tick.timestamp,
                )
            )
            return

        ladder = self._target_ladder(outcome)
        progress = _LADDER_PROGRESS[outcome.status]
        if progress >= len(ladder):
            return
        target, level, status = ladder[progress]
        if not _crossed(outcome.direction, mark_price, level, favorable=True):
            return

        is_final = progress == len(ladder) - 1
        if is_final:
            self._resolve(outcome, target, mark_price, tick.timestamp, status)
        else:
            outcome.status = status
            self._repository.save_outcome(outcome)
        await self._event_bus.publish(
            TakeProfitHit(
                outcome_id=outcome.id,
                symbol=outcome.symbol,
                target=target,
                price=mark_price,
                pips=pips,
                at=tick.timestamp,
            )
        )

    async def _process_pending(self, outcome: SignalOutcome, tick: Tick) -> None:
        assert outcome.trigger_price is not None  # PENDING implies a trigger was set
        # A buy-stop triggers when the ask reaches it (a market buy fills at
        # ask); a sell-stop triggers when the bid reaches it.
        trigger_price = tick.ask if outcome.direction is Direction.LONG else tick.bid
        triggered = _crossed(
            outcome.direction, trigger_price, outcome.trigger_price, favorable=True
        )
        if triggered:
            outcome.status = OutcomeStatus.ACTIVE
            outcome.timestamp_triggered = tick.timestamp
            self._repository.save_outcome(outcome)
            await self._event_bus.publish(
                SignalTriggered(
                    outcome_id=outcome.id,
                    symbol=outcome.symbol,
                    trigger_price=outcome.trigger_price,
                    at=tick.timestamp,
                )
            )
            return

        if tick.timestamp - outcome.timestamp_generated >= self._expiry:
            self._resolve(outcome, None, trigger_price, tick.timestamp, OutcomeStatus.EXPIRED)
            await self._event_bus.publish(
                SignalExpired(outcome_id=outcome.id, symbol=outcome.symbol, at=tick.timestamp)
            )

    def _target_ladder(
        self, outcome: SignalOutcome
    ) -> list[tuple[HitTarget, float, OutcomeStatus]]:
        ladder: list[tuple[HitTarget, float, OutcomeStatus]] = [
            (HitTarget.TP1, outcome.take_profit_1, OutcomeStatus.TP1_HIT)
        ]
        if outcome.take_profit_2 is not None:
            ladder.append((HitTarget.TP2, outcome.take_profit_2, OutcomeStatus.TP2_HIT))
        if outcome.take_profit_3 is not None:
            ladder.append((HitTarget.TP3, outcome.take_profit_3, OutcomeStatus.TP3_HIT))
        return ladder

    def _sample_if_due(self, outcome: SignalOutcome, price: float, at: datetime) -> None:
        last = outcome.live_price_samples[-1] if outcome.live_price_samples else None
        if last is not None and at - last.at < self._sample_interval:
            return
        outcome.live_price_samples.append(LivePriceSample(price=price, at=at))
        self._repository.record_outcome_sample(outcome.id, price=price, at=at)

    def _resolve(
        self,
        outcome: SignalOutcome,
        target: HitTarget | None,
        price: float,
        at: datetime,
        status: OutcomeStatus,
    ) -> None:
        outcome.status = status
        outcome.hit_target = target
        outcome.timestamp_resolved = at
        outcome.final_pips = outcome.pips(price)
        risk_pips = abs(outcome.entry_price - outcome.stop_loss) / outcome.pip_size
        outcome.achieved_risk_reward = outcome.final_pips / risk_pips if risk_pips > 0 else None
        outcome.highest_pips = max(outcome.highest_pips, outcome.final_pips)
        outcome.lowest_pips = min(outcome.lowest_pips, outcome.final_pips)
        self._open.pop(outcome.id, None)
        self._repository.save_outcome(outcome)


__all__ = ["SignalLifecycleTracker"]
