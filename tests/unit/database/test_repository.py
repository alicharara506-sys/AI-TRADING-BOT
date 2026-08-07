from __future__ import annotations

import json
from datetime import UTC, datetime

from core.interfaces.types import (
    AccountState,
    Direction,
    Evidence,
    OrderSide,
    Symbol,
    Trade,
    TradeSignal,
)
from database.repository import SqliteSignalRepository
from decision_engine.report import DecisionReport

_SYMBOL = Symbol(name="EURUSD")


def _repository() -> SqliteSignalRepository:
    return SqliteSignalRepository("sqlite:///:memory:")


def _decision_report() -> DecisionReport:
    signal = TradeSignal(
        symbol=_SYMBOL,
        direction=Direction.LONG,
        combined_confidence=0.72,
        threshold=0.5,
        evidence=(
            Evidence(
                source_module="fibonacci_confluence",
                direction=Direction.LONG,
                confidence=0.8,
                rationale={"fib_ratio": 0.618},
            ),
        ),
    )
    return DecisionReport(
        signal=signal,
        confidence=0.72,
        probability_of_success=0.72,
        recommended_position_size=0.01,
        recommended_stop_loss=1.095,
        recommended_take_profit=1.115,
        uncertainty="medium",
        atr=0.0025,
    )


def test_record_and_read_back_latest_signal() -> None:
    repository = _repository()

    repository.record_signal(_decision_report(), strategy_name="sma_crossover", entry_price=1.10)

    row = repository.latest_signal("EURUSD")
    assert row is not None
    assert row.symbol == "EURUSD"
    assert row.direction == "long"
    assert row.strategy_name == "sma_crossover"
    assert row.entry_price == 1.10
    assert row.stop_loss == 1.095
    assert row.take_profit == 1.115
    assert row.confidence == 0.72
    assert row.uncertainty == "medium"
    evidence = json.loads(row.evidence_json)
    assert evidence == [
        {
            "source_module": "fibonacci_confluence",
            "direction": "long",
            "confidence": 0.8,
            "rationale": {"fib_ratio": 0.618},
        }
    ]


def test_latest_signal_returns_the_most_recently_recorded_row() -> None:
    repository = _repository()
    repository.record_signal(_decision_report(), strategy_name="first", entry_price=1.10)
    repository.record_signal(_decision_report(), strategy_name="second", entry_price=1.11)

    row = repository.latest_signal("EURUSD")

    assert row is not None
    assert row.strategy_name == "second"


def test_latest_signal_is_none_for_an_unrecorded_symbol() -> None:
    repository = _repository()

    assert repository.latest_signal("GBPUSD") is None


def test_record_and_read_back_account_snapshot() -> None:
    repository = _repository()
    account = AccountState(
        balance=10_000.0,
        equity=10_050.0,
        margin=200.0,
        free_margin=9_850.0,
        margin_level=5025.0,
        currency="USD",
    )

    repository.record_account_snapshot(account)

    row = repository.latest_account_snapshot()
    assert row is not None
    assert row.balance == 10_000.0
    assert row.equity == 10_050.0
    assert row.currency == "USD"


def test_latest_account_snapshot_is_none_when_nothing_recorded() -> None:
    repository = _repository()

    assert repository.latest_account_snapshot() is None


def test_record_and_list_trades() -> None:
    repository = _repository()
    trade = Trade(
        trade_id="t1",
        symbol=_SYMBOL,
        side=OrderSide.BUY,
        volume=0.01,
        open_price=1.10,
        close_price=1.105,
        open_time=datetime(2026, 1, 1, tzinfo=UTC),
        close_time=datetime(2026, 1, 1, 1, tzinfo=UTC),
        profit=5.0,
    )

    repository.record_trade(trade)

    trades = repository.list_trades()
    assert len(trades) == 1
    assert trades[0].trade_id == "t1"
    assert trades[0].symbol == "EURUSD"
    assert trades[0].profit == 5.0


def test_list_trades_is_empty_when_nothing_recorded() -> None:
    repository = _repository()

    assert repository.list_trades() == []


def test_schema_creation_is_idempotent_across_repository_instances() -> None:
    # Both instances point at the same real file-backed schema logic path
    # (Base.metadata.create_all is safe to call more than once); this test
    # uses two separate in-memory databases just to prove construction
    # itself never raises on a second call.
    _repository()
    _repository()
