from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from core.interfaces.types import Direction
from database.repository import SqliteSignalRepository
from live_tracking.types import HitTarget, OutcomeStatus, SignalOutcome


def _repository() -> SqliteSignalRepository:
    return SqliteSignalRepository("sqlite:///:memory:")


def _outcome(**overrides: object) -> SignalOutcome:
    defaults: dict[str, object] = {
        "id": "o1",
        "symbol": "XAUUSD",
        "direction": Direction.LONG,
        "strategy_name": "signal_fusion",
        "entry_price": 4348.27,
        "stop_loss": 4327.20,
        "take_profit_1": 4368.00,
        "pip_size": 0.1,
        "timestamp_generated": datetime(2026, 1, 1, tzinfo=UTC),
        "score_at_generation": 0.66,
        "uncertainty_at_generation": "medium",
    }
    defaults.update(overrides)
    return SignalOutcome(**defaults)  # type: ignore[arg-type]


def test_save_and_get_outcome_round_trips_all_fields() -> None:
    repository = _repository()
    outcome = _outcome(take_profit_2=4387.20, take_profit_3=4407.20)

    repository.save_outcome(outcome)

    row = repository.get_outcome("o1")
    assert row is not None
    assert row.symbol == "XAUUSD"
    assert row.direction == "long"
    assert row.entry_price == 4348.27
    assert row.take_profit_2 == 4387.20
    assert row.status == "active"
    assert row.user_reactions_json == "[]"


def test_save_outcome_is_an_upsert_by_id() -> None:
    repository = _repository()
    outcome = _outcome()
    repository.save_outcome(outcome)

    outcome.status = OutcomeStatus.TP1_HIT
    outcome.hit_target = HitTarget.TP1
    outcome.highest_pips = 197.3
    outcome.timestamp_resolved = datetime(2026, 1, 1, 2, tzinfo=UTC)
    repository.save_outcome(outcome)

    row = repository.get_outcome("o1")
    assert row is not None
    assert row.status == "tp1_hit"
    assert row.hit_target == "TP1"
    assert row.highest_pips == 197.3
    assert len(repository.list_outcomes()) == 1


def test_list_open_outcomes_excludes_resolved_outcomes() -> None:
    repository = _repository()
    open_outcome = _outcome(id="open1")
    resolved_outcome = _outcome(id="resolved1")
    resolved_outcome.status = OutcomeStatus.SL_HIT
    resolved_outcome.timestamp_resolved = datetime(2026, 1, 1, 1, tzinfo=UTC)
    repository.save_outcome(open_outcome)
    repository.save_outcome(resolved_outcome)

    open_ids = {row.id for row in repository.list_open_outcomes()}

    assert open_ids == {"open1"}


def test_list_outcomes_filters_by_symbol() -> None:
    repository = _repository()
    repository.save_outcome(_outcome(id="a", symbol="XAUUSD"))
    repository.save_outcome(_outcome(id="b", symbol="EURUSD"))

    rows = repository.list_outcomes(symbol="eurusd")

    assert [row.id for row in rows] == ["b"]


def test_record_and_list_outcome_samples_in_chronological_order() -> None:
    repository = _repository()
    repository.save_outcome(_outcome())

    first_at = datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)
    second_at = datetime(2026, 1, 1, 0, 0, 10, tzinfo=UTC)
    repository.record_outcome_sample("o1", price=4350.0, at=first_at)
    repository.record_outcome_sample("o1", price=4351.0, at=second_at)

    samples = repository.list_outcome_samples("o1")

    assert [s.price for s in samples] == [4350.0, 4351.0]


def test_add_reaction_appends_to_existing_reactions() -> None:
    repository = _repository()
    repository.save_outcome(_outcome())

    repository.add_reaction("o1", "fire")
    repository.add_reaction("o1", "heart")

    row = repository.get_outcome("o1")
    assert row is not None
    assert json.loads(row.user_reactions_json) == ["fire", "heart"]


def test_add_reaction_raises_for_unknown_outcome() -> None:
    repository = _repository()
    with pytest.raises(ValueError):
        repository.add_reaction("missing", "fire")


def test_set_user_note_updates_the_note() -> None:
    repository = _repository()
    repository.save_outcome(_outcome())

    repository.set_user_note("o1", "watching for a retest of entry")

    row = repository.get_outcome("o1")
    assert row is not None
    assert row.user_note == "watching for a retest of entry"


def test_set_user_note_raises_for_unknown_outcome() -> None:
    repository = _repository()
    with pytest.raises(ValueError):
        repository.set_user_note("missing", "note")
