from __future__ import annotations

from core.interfaces.validation import ValidationReport
from optimization.result import OptimizationTrial
from research_lab.experiment_log import ExperimentLog, ExperimentRecord


def record_optimization_trial(
    log: ExperimentLog,
    *,
    subject_name: str,
    trial: OptimizationTrial,
    hypothesis: str | None = None,
) -> tuple[ExperimentRecord, bool]:
    """Wraps a Phase 9 OptimizationTrial into a durable, replayable
    experiment record -- the trial's own shape (parameters, in/out-of-sample
    scores, degradation) is already correct, it just wasn't logged across
    runs before.
    """
    return log.record(
        kind="optimization_trial",
        subject_name=subject_name,
        parameters=trial.parameters,
        outcome={
            "in_sample_score": trial.in_sample_score,
            "out_of_sample_score": trial.out_of_sample_score,
            "degradation": trial.degradation,
        },
        hypothesis=hypothesis,
    )


def record_validation_report(
    log: ExperimentLog,
    *,
    report: ValidationReport,
    hypothesis: str | None = None,
) -> tuple[ExperimentRecord, bool]:
    """Wraps a Phase 8 ValidationReport into a durable experiment record.
    The parameters field records which checks ran (the report itself has no
    strategy parameters to log); the outcome records the pass/fail verdict
    of every individual check, not just the aggregate.
    """
    return log.record(
        kind="validation_report",
        subject_name=report.strategy_name,
        parameters={"checks": [check.name for check in report.checks]},
        outcome={
            "passed": report.passed,
            "failure_summary": report.failure_summary(),
            **{f"check_{check.name}": check.passed for check in report.checks},
        },
        hypothesis=hypothesis,
    )


__all__ = ["record_optimization_trial", "record_validation_report"]
