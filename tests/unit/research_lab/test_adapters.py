from __future__ import annotations

from datetime import UTC, datetime

from core.interfaces.validation import CheckResult, ValidationReport
from core.kernel.clock import TestClock
from optimization.result import OptimizationTrial
from research_lab.adapters import record_optimization_trial, record_validation_report
from research_lab.experiment_log import ExperimentLog


def test_record_optimization_trial_preserves_scores_and_degradation() -> None:
    log = ExperimentLog(clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))
    trial = OptimizationTrial(
        parameters={"fast": 5, "slow": 20}, in_sample_score=10.0, out_of_sample_score=8.0
    )

    record, is_new = record_optimization_trial(log, subject_name="sma_cross", trial=trial)

    assert is_new is True
    assert record.kind == "optimization_trial"
    assert record.parameters == {"fast": 5, "slow": 20}
    assert record.outcome["in_sample_score"] == 10.0
    assert record.outcome["out_of_sample_score"] == 8.0
    assert record.outcome["degradation"] == trial.degradation


def test_record_optimization_trial_is_idempotent_through_the_log() -> None:
    log = ExperimentLog(clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))
    trial = OptimizationTrial(
        parameters={"fast": 5, "slow": 20}, in_sample_score=10.0, out_of_sample_score=8.0
    )

    record_optimization_trial(log, subject_name="sma_cross", trial=trial)
    _, is_new = record_optimization_trial(log, subject_name="sma_cross", trial=trial)

    assert is_new is False
    assert len(log.history()) == 1


def test_record_validation_report_captures_every_check() -> None:
    log = ExperimentLog(clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))
    report = ValidationReport(
        strategy_name="my_strategy",
        checks=(
            CheckResult(name="walk_forward", passed=True),
            CheckResult(name="monte_carlo_drawdown", passed=False, detail={"drawdown": 45.0}),
        ),
    )

    record, is_new = record_validation_report(log, report=report)

    assert is_new is True
    assert record.kind == "validation_report"
    assert record.subject_name == "my_strategy"
    assert record.outcome["passed"] is False
    assert record.outcome["check_walk_forward"] is True
    assert record.outcome["check_monte_carlo_drawdown"] is False
    assert "monte_carlo_drawdown" in record.outcome["failure_summary"]
