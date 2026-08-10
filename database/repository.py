"""Persistence for the dashboard: a narrow SignalRepository Protocol plus a
SQLite-backed implementation, following the same swappable-Protocol pattern
already used for Connector/NewsProvider/SizingModel elsewhere in this
platform. SQLite is a deliberate choice for a single-user local platform;
a Postgres-backed implementation could satisfy the same Protocol later
without any caller (run_dashboard_feed.py, the Streamlit app) changing.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from core.interfaces.types import AccountState, Bar, Trade
from database.models import (
    Base,
    RecordedAccountSnapshot,
    RecordedBar,
    RecordedOutcome,
    RecordedOutcomeSample,
    RecordedSignal,
    RecordedTrade,
)
from decision_engine.report import DecisionReport
from live_tracking.types import SignalOutcome


@runtime_checkable
class SignalRepository(Protocol):
    def record_signal(
        self, report: DecisionReport, *, strategy_name: str, entry_price: float | None
    ) -> None: ...

    def record_account_snapshot(self, account: AccountState) -> None: ...

    def record_trade(self, trade: Trade) -> None: ...

    def record_bar(self, bar: Bar) -> None: ...

    def bulk_record_bars(self, bars: Sequence[Bar]) -> None: ...

    def latest_signal(self, symbol: str) -> RecordedSignal | None: ...

    def latest_account_snapshot(self) -> RecordedAccountSnapshot | None: ...

    def list_trades(self, *, limit: int = 500) -> list[RecordedTrade]: ...

    def list_recent_bars(
        self, symbol: str, timeframe: str, *, limit: int = 500
    ) -> list[RecordedBar]: ...

    def save_outcome(self, outcome: SignalOutcome) -> None: ...

    def record_outcome_sample(self, outcome_id: str, *, price: float, at: datetime) -> None: ...

    def get_outcome(self, outcome_id: str) -> RecordedOutcome | None: ...

    def list_open_outcomes(self) -> list[RecordedOutcome]: ...

    def list_outcomes(
        self, *, symbol: str | None = None, limit: int = 500
    ) -> list[RecordedOutcome]: ...

    def list_outcome_samples(
        self, outcome_id: str, *, limit: int = 500
    ) -> list[RecordedOutcomeSample]: ...

    def add_reaction(self, outcome_id: str, reaction: str) -> None: ...

    def set_user_note(self, outcome_id: str, note: str) -> None: ...


class SqliteSignalRepository:
    """SignalRepository backed by a SQLite file (or `sqlite:///:memory:` for
    tests). Creates the schema on construction if it doesn't already exist
    -- idempotent, so both run_dashboard_feed.py and the Streamlit app can
    open the same file without a separate migration step.
    """

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url)
        Base.metadata.create_all(self._engine)

    def record_signal(
        self, report: DecisionReport, *, strategy_name: str, entry_price: float | None
    ) -> None:
        evidence_json = json.dumps(
            [
                {
                    "source_module": item.source_module,
                    "direction": item.direction.value,
                    "confidence": item.confidence,
                    "rationale": item.rationale,
                }
                for item in report.signal.evidence
            ]
        )
        row = RecordedSignal(
            symbol=report.signal.symbol.canonical,
            direction=report.signal.direction.value,
            strategy_name=strategy_name,
            entry_price=entry_price,
            stop_loss=report.recommended_stop_loss,
            take_profit=report.recommended_take_profit,
            confidence=report.confidence,
            uncertainty=report.uncertainty,
            atr=report.atr,
            evidence_json=evidence_json,
            timestamp=datetime.utcnow(),
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()

    def record_account_snapshot(self, account: AccountState) -> None:
        row = RecordedAccountSnapshot(
            balance=account.balance,
            equity=account.equity,
            margin=account.margin,
            free_margin=account.free_margin,
            margin_level=account.margin_level,
            currency=account.currency,
            timestamp=datetime.utcnow(),
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()

    def record_trade(self, trade: Trade) -> None:
        row = RecordedTrade(
            trade_id=trade.trade_id,
            symbol=trade.symbol.canonical,
            side=trade.side.value,
            volume=trade.volume,
            open_price=trade.open_price,
            close_price=trade.close_price,
            open_time=trade.open_time,
            close_time=trade.close_time,
            profit=trade.profit,
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()

    def latest_signal(self, symbol: str) -> RecordedSignal | None:
        statement = (
            select(RecordedSignal)
            .where(RecordedSignal.symbol == symbol.upper())
            .order_by(RecordedSignal.timestamp.desc())
            .limit(1)
        )
        with Session(self._engine) as session:
            return session.execute(statement).scalar_one_or_none()

    def latest_account_snapshot(self) -> RecordedAccountSnapshot | None:
        statement = select(RecordedAccountSnapshot).order_by(
            RecordedAccountSnapshot.timestamp.desc()
        ).limit(1)
        with Session(self._engine) as session:
            return session.execute(statement).scalar_one_or_none()

    def list_trades(self, *, limit: int = 500) -> list[RecordedTrade]:
        statement = select(RecordedTrade).order_by(RecordedTrade.close_time.desc()).limit(limit)
        with Session(self._engine) as session:
            return list(session.execute(statement).scalars().all())

    def record_bar(self, bar: Bar) -> None:
        self._upsert_bars([bar])

    def bulk_record_bars(self, bars: Sequence[Bar]) -> None:
        self._upsert_bars(bars)

    def _upsert_bars(self, bars: Sequence[Bar]) -> None:
        if not bars:
            return
        rows = [
            {
                "symbol": bar.symbol.canonical,
                "timeframe": bar.timeframe.value,
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
        # SQLite-specific upsert: bars can legitimately be re-fetched (the
        # historical backfill and the live BarClosed stream overlap at the
        # boundary), and duplicates would silently corrupt the chart with
        # repeated timestamps -- on_conflict_do_nothing relies on the
        # (symbol, timeframe, timestamp) unique constraint in models.py.
        statement = sqlite_insert(RecordedBar).values(rows).on_conflict_do_nothing(
            index_elements=["symbol", "timeframe", "timestamp"]
        )
        with Session(self._engine) as session:
            session.execute(statement)
            session.commit()

    def list_recent_bars(
        self, symbol: str, timeframe: str, *, limit: int = 500
    ) -> list[RecordedBar]:
        statement = (
            select(RecordedBar)
            .where(RecordedBar.symbol == symbol.upper(), RecordedBar.timeframe == timeframe)
            .order_by(RecordedBar.timestamp.desc())
            .limit(limit)
        )
        with Session(self._engine) as session:
            rows = list(session.execute(statement).scalars().all())
        rows.reverse()
        return rows

    def save_outcome(self, outcome: SignalOutcome) -> None:
        """Insert-or-update by outcome.id -- SignalLifecycleTracker calls this
        after every state change (trigger, a new highest/lowest pip extreme, a
        target/stop hit), so this must be a real upsert, not the
        on_conflict_do_nothing used for bars (which are legitimately
        immutable once closed).
        """
        row = {
            "id": outcome.id,
            "symbol": outcome.symbol,
            "direction": outcome.direction.value,
            "strategy_name": outcome.strategy_name,
            "entry_price": outcome.entry_price,
            "trigger_price": outcome.trigger_price,
            "stop_loss": outcome.stop_loss,
            "take_profit_1": outcome.take_profit_1,
            "take_profit_2": outcome.take_profit_2,
            "take_profit_3": outcome.take_profit_3,
            "pip_size": outcome.pip_size,
            "status": outcome.status.value,
            "highest_pips": outcome.highest_pips,
            "lowest_pips": outcome.lowest_pips,
            "final_pips": outcome.final_pips,
            "achieved_risk_reward": outcome.achieved_risk_reward,
            "score_at_generation": outcome.score_at_generation,
            "uncertainty_at_generation": outcome.uncertainty_at_generation,
            "regime_at_generation": outcome.regime_at_generation,
            "sentiment_at_generation": outcome.sentiment_at_generation,
            "ml_probability_at_generation": outcome.ml_probability_at_generation,
            "timestamp_generated": outcome.timestamp_generated,
            "timestamp_triggered": outcome.timestamp_triggered,
            "timestamp_resolved": outcome.timestamp_resolved,
            "hit_target": outcome.hit_target.value if outcome.hit_target else None,
            "user_note": outcome.user_note,
            "user_reactions_json": json.dumps(outcome.user_reactions),
        }
        statement = sqlite_insert(RecordedOutcome).values(**row)
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={key: statement.excluded[key] for key in row if key != "id"},
        )
        with Session(self._engine) as session:
            session.execute(statement)
            session.commit()

    def record_outcome_sample(self, outcome_id: str, *, price: float, at: datetime) -> None:
        row = RecordedOutcomeSample(outcome_id=outcome_id, price=price, timestamp=at)
        with Session(self._engine) as session:
            session.add(row)
            session.commit()

    def get_outcome(self, outcome_id: str) -> RecordedOutcome | None:
        with Session(self._engine) as session:
            return session.get(RecordedOutcome, outcome_id)

    def list_open_outcomes(self) -> list[RecordedOutcome]:
        """"Open" is defined by timestamp_resolved being unset, not by
        status value: TP1_HIT/TP2_HIT are frequently *not* terminal (see
        live_tracking/types.py's OutcomeStatus docstring) -- only
        SignalLifecycleTracker itself knows, per outcome, whether a given
        partial-target hit was the final configured target, and it is the
        one that sets timestamp_resolved when it decides an outcome is
        actually done.
        """
        statement = select(RecordedOutcome).where(RecordedOutcome.timestamp_resolved.is_(None))
        with Session(self._engine) as session:
            return list(session.execute(statement).scalars().all())

    def list_outcomes(
        self, *, symbol: str | None = None, limit: int = 500
    ) -> list[RecordedOutcome]:
        statement = select(RecordedOutcome).order_by(RecordedOutcome.timestamp_generated.desc())
        if symbol is not None:
            statement = statement.where(RecordedOutcome.symbol == symbol.upper())
        statement = statement.limit(limit)
        with Session(self._engine) as session:
            return list(session.execute(statement).scalars().all())

    def list_outcome_samples(
        self, outcome_id: str, *, limit: int = 500
    ) -> list[RecordedOutcomeSample]:
        statement = (
            select(RecordedOutcomeSample)
            .where(RecordedOutcomeSample.outcome_id == outcome_id)
            .order_by(RecordedOutcomeSample.timestamp.desc())
            .limit(limit)
        )
        with Session(self._engine) as session:
            rows = list(session.execute(statement).scalars().all())
        rows.reverse()
        return rows

    def add_reaction(self, outcome_id: str, reaction: str) -> None:
        with Session(self._engine) as session:
            row = session.get(RecordedOutcome, outcome_id)
            if row is None:
                raise ValueError(f"no recorded outcome with id '{outcome_id}'")
            reactions = json.loads(row.user_reactions_json)
            reactions.append(reaction)
            row.user_reactions_json = json.dumps(reactions)
            session.commit()

    def set_user_note(self, outcome_id: str, note: str) -> None:
        with Session(self._engine) as session:
            row = session.get(RecordedOutcome, outcome_id)
            if row is None:
                raise ValueError(f"no recorded outcome with id '{outcome_id}'")
            row.user_note = note
            session.commit()


__all__ = ["SignalRepository", "SqliteSignalRepository"]
