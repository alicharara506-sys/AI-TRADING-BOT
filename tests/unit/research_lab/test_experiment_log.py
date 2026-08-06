from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.kernel.clock import TestClock
from research_lab.experiment_log import ExperimentLog, compute_experiment_id


@pytest.fixture
def clock() -> TestClock:
    return TestClock(datetime(2026, 1, 1, tzinfo=UTC))


def test_compute_experiment_id_is_independent_of_parameter_key_order() -> None:
    id_a = compute_experiment_id(kind="k", subject_name="s", parameters={"a": 1, "b": 2})
    id_b = compute_experiment_id(kind="k", subject_name="s", parameters={"b": 2, "a": 1})

    assert id_a == id_b


def test_recording_an_identical_experiment_twice_is_idempotent(clock: TestClock) -> None:
    log = ExperimentLog(clock=clock)
    params = {"fast": 5, "slow": 20}

    first, first_is_new = log.record(
        kind="optimization_trial", subject_name="sma_cross", parameters=params,
        outcome={"score": 1.2},
    )
    second, second_is_new = log.record(
        kind="optimization_trial", subject_name="sma_cross", parameters=params,
        outcome={"score": 999.0},
    )

    assert first_is_new is True
    assert second_is_new is False
    assert first.experiment_id == second.experiment_id
    assert second.outcome == {"score": 1.2}
    assert len(log.history()) == 1


def test_distinct_parameters_produce_distinct_records(clock: TestClock) -> None:
    log = ExperimentLog(clock=clock)
    log.record(
        kind="optimization_trial", subject_name="sma_cross",
        parameters={"fast": 5, "slow": 20}, outcome={"score": 1.2},
    )
    log.record(
        kind="optimization_trial", subject_name="sma_cross",
        parameters={"fast": 5, "slow": 25}, outcome={"score": 1.5},
    )

    assert len(log.history()) == 2
    best = log.best("sma_cross", outcome_key="score")
    assert best.parameters == {"fast": 5, "slow": 25}


def test_by_subject_and_by_kind_filter_correctly(clock: TestClock) -> None:
    log = ExperimentLog(clock=clock)
    log.record(
        kind="optimization_trial", subject_name="a", parameters={"x": 1}, outcome={"score": 1.0}
    )
    log.record(
        kind="validation_report", subject_name="a", parameters={"x": 2}, outcome={"passed": True}
    )
    log.record(
        kind="optimization_trial", subject_name="b", parameters={"x": 3}, outcome={"score": 2.0}
    )

    assert len(log.by_subject("a")) == 2
    assert len(log.by_kind("optimization_trial")) == 2
    assert len(log.by_kind("validation_report")) == 1


def test_best_ignores_records_with_a_different_outcome_shape(clock: TestClock) -> None:
    """A subject can accumulate heterogeneous experiment kinds -- e.g. both
    optimization trials and validation reports -- whose outcome dicts don't
    share keys. best() must skip records missing the requested key rather
    than crash on the first mismatched one it encounters.
    """
    log = ExperimentLog(clock=clock)
    log.record(
        kind="validation_report", subject_name="s", parameters={"checks": ["x"]},
        outcome={"passed": True},
    )
    log.record(
        kind="optimization_trial", subject_name="s", parameters={"p": 1},
        outcome={"out_of_sample_score": 1.5},
    )

    best = log.best("s", outcome_key="out_of_sample_score")

    assert best.kind == "optimization_trial"
    assert best.outcome == {"out_of_sample_score": 1.5}


def test_best_raises_when_no_record_carries_the_outcome_key(clock: TestClock) -> None:
    log = ExperimentLog(clock=clock)
    log.record(
        kind="validation_report", subject_name="s", parameters={}, outcome={"passed": True}
    )

    with pytest.raises(ValueError, match="no experiments for subject 's' carry outcome key"):
        log.best("s", outcome_key="out_of_sample_score")


def test_best_raises_for_unknown_subject(clock: TestClock) -> None:
    log = ExperimentLog(clock=clock)

    with pytest.raises(ValueError, match="no experiments recorded"):
        log.best("nonexistent", outcome_key="score")


def test_best_respects_higher_or_lower_is_better(clock: TestClock) -> None:
    log = ExperimentLog(clock=clock)
    log.record(kind="k", subject_name="s", parameters={"p": 1}, outcome={"drawdown": 5.0})
    log.record(kind="k", subject_name="s", parameters={"p": 2}, outcome={"drawdown": 2.0})

    assert log.best("s", outcome_key="drawdown", higher_is_better=True).parameters == {"p": 1}
    assert log.best("s", outcome_key="drawdown", higher_is_better=False).parameters == {"p": 2}


def test_persistence_survives_a_fresh_instance_via_replay(
    tmp_path: Path, clock: TestClock
) -> None:
    path = tmp_path / "log.jsonl"
    first_instance = ExperimentLog(path=path, clock=clock)
    first_instance.record(
        kind="optimization_trial", subject_name="x", parameters={"p": 1}, outcome={"score": 3.0}
    )
    first_instance.record(
        kind="optimization_trial", subject_name="x", parameters={"p": 2}, outcome={"score": 4.0}
    )

    second_instance = ExperimentLog(path=path, clock=clock)

    assert len(second_instance.history()) == 2
    assert second_instance.best("x", outcome_key="score").outcome == {"score": 4.0}


def test_replayed_log_still_dedupes_against_disk_history(
    tmp_path: Path, clock: TestClock
) -> None:
    path = tmp_path / "log.jsonl"
    ExperimentLog(path=path, clock=clock).record(
        kind="optimization_trial", subject_name="x", parameters={"p": 1}, outcome={"score": 3.0}
    )

    reloaded = ExperimentLog(path=path, clock=clock)
    _, is_new = reloaded.record(
        kind="optimization_trial", subject_name="x", parameters={"p": 1}, outcome={"score": 999.0}
    )

    assert is_new is False
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_hypothesis_and_metadata_are_recorded(clock: TestClock) -> None:
    log = ExperimentLog(clock=clock)

    record, _ = log.record(
        kind="optimization_trial",
        subject_name="s",
        parameters={"p": 1},
        outcome={"score": 1.0},
        hypothesis="wider stops reduce whipsaw losses",
        metadata={"data_window": "2025-01-01/2025-06-01"},
    )

    assert record.hypothesis == "wider stops reduce whipsaw losses"
    assert record.metadata == {"data_window": "2025-01-01/2025-06-01"}
    assert record.recorded_at == clock.now()
