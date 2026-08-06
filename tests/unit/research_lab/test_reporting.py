from __future__ import annotations

from datetime import UTC, datetime

from core.kernel.clock import TestClock
from research_lab.experiment_log import ExperimentLog
from research_lab.reporting import render_subject_report


def test_render_subject_report_with_no_experiments() -> None:
    log = ExperimentLog(clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))

    text = render_subject_report(log, "nonexistent", outcome_key="score")

    assert "No experiments recorded" in text


def test_render_subject_report_includes_best_and_spread() -> None:
    log = ExperimentLog(clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))
    log.record(
        kind="optimization_trial", subject_name="sma_cross",
        parameters={"fast": 5, "slow": 20}, outcome={"score": 1.2},
        hypothesis="faster crossover reduces lag",
    )
    log.record(
        kind="optimization_trial", subject_name="sma_cross",
        parameters={"fast": 5, "slow": 25}, outcome={"score": 1.5},
    )

    text = render_subject_report(log, "sma_cross", outcome_key="score")

    assert "Runs: 2 total" in text
    assert "carrying" not in text  # every record here carries 'score' -- no need to qualify
    assert "Best score: 1.5" in text
    assert "'fast': 5, 'slow': 25" in text
    assert "faster crossover reduces lag" not in text  # best run has no hypothesis of its own
    assert "mean=1.35" in text


def test_render_subject_report_qualifies_the_run_count_for_heterogeneous_kinds() -> None:
    log = ExperimentLog(clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))
    log.record(
        kind="validation_report", subject_name="sma_cross", parameters={"checks": ["x"]},
        outcome={"passed": True},
    )
    log.record(
        kind="optimization_trial", subject_name="sma_cross", parameters={"fast": 5},
        outcome={"score": 1.2},
    )

    text = render_subject_report(log, "sma_cross", outcome_key="score")

    assert "Runs: 2 total (1 carrying 'score')" in text
