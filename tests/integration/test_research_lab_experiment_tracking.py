from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backtesting.validation.look_ahead import LookAheadBiasCheck
from backtesting.validation.monte_carlo import MonteCarloCheck
from backtesting.validation.pipeline import ValidationPipeline
from backtesting.validation.walk_forward import WalkForwardCheck
from core.kernel.clock import TestClock
from optimization.algorithms.grid_search import GridSearchOptimizer
from optimization.result import OptimizationTrial
from research_lab.adapters import record_optimization_trial, record_validation_report
from research_lab.experiment_log import ExperimentLog
from research_lab.reporting import render_subject_report
from research_lab.significance import welch_t_test

# Simple, verified evaluator: in-sample score peaks at fast=5, and every
# trial degrades out-of-sample by a fixed 20% -- deterministic, so the
# "best" trial is known ahead of time and the test isn't just asserting
# whatever the code happens to produce.
_TARGET_FAST = 5


class _DeterministicEvaluator:
    def evaluate(self, parameters: dict[str, Any]) -> tuple[float, float]:
        in_sample = 10.0 - abs(parameters["fast"] - _TARGET_FAST)
        out_of_sample = in_sample * 0.8
        return in_sample, out_of_sample


def test_optimization_sweep_is_durably_logged_and_survives_a_restart(
    tmp_path: Path,
) -> None:
    """Phase 6 exit criteria, part 1: a real GridSearchOptimizer sweep is
    recorded trial-by-trial into an ExperimentLog, re-running the identical
    sweep doesn't double-count it, and a fresh ExperimentLog instance
    pointed at the same file recovers the full history -- proving the
    append-only-log-with-replay pattern actually survives a "process
    restart," not just an in-memory round trip.
    """
    log_path = tmp_path / "optimization_runs.jsonl"
    optimizer = GridSearchOptimizer({"fast": [1, 3, 5, 7, 9]})
    result = optimizer.run(_DeterministicEvaluator())
    assert len(result.trials) == 5

    log = ExperimentLog(path=log_path, clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))
    for trial in result.trials:
        record, is_new = record_optimization_trial(
            log, subject_name="sma_cross", trial=trial, hypothesis="fast=5 is optimal"
        )
        assert is_new is True

    assert len(log.history()) == 5

    # Re-running the identical sweep and re-recording every trial must be a
    # no-op -- this is the whole point of the composite dedup key.
    for trial in optimizer.run(_DeterministicEvaluator()).trials:
        _, is_new = record_optimization_trial(log, subject_name="sma_cross", trial=trial)
        assert is_new is False
    assert len(log.history()) == 5

    best_from_log = log.best("sma_cross", outcome_key="out_of_sample_score")
    best_from_result = result.best()
    assert best_from_log.parameters == best_from_result.parameters
    assert best_from_log.parameters == {"fast": _TARGET_FAST}

    # Simulate a restart: a brand new ExperimentLog instance, same file.
    reloaded = ExperimentLog(path=log_path, clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))
    assert len(reloaded.history()) == 5
    assert reloaded.best("sma_cross", outcome_key="out_of_sample_score").parameters == {
        "fast": _TARGET_FAST
    }


def test_validation_report_and_significance_and_reporting_end_to_end() -> None:
    """Phase 6 exit criteria, part 2: a real Phase 8 ValidationPipeline
    report is logged through the same framework, a real statistical
    significance test distinguishes a genuinely better parameter region
    from a worse one, and the auto-generated report surfaces both.
    """
    log = ExperimentLog(clock=TestClock(datetime(2026, 1, 1, tzinfo=UTC)))

    pipeline = ValidationPipeline(
        walk_forward=WalkForwardCheck(max_degradation=0.5),
        monte_carlo=MonteCarloCheck(max_drawdown=30.0, iterations=200, seed=1),
        look_ahead=LookAheadBiasCheck(),
    )
    robust_returns = [10, -4, 8, -3, 9, -5, 7, -2, 10, -4, 9, -5, 8, -3, 7, -4, 10, -2, 9, -3]
    timestamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(20)]
    report = pipeline.run(
        strategy_name="sma_cross", trade_returns=robust_returns, bar_timestamps=timestamps
    )
    assert report.passed

    validation_record, is_new = record_validation_report(log, report=report)
    assert is_new is True
    assert validation_record.outcome["passed"] is True

    good_region_scores = [10.0 - abs(f - _TARGET_FAST) * 0.8 for f in (4, 5, 6, 5, 4, 6, 5)]
    bad_region_scores = [10.0 - abs(f - _TARGET_FAST) * 0.8 for f in (20, 22, 19, 21, 20, 23, 18)]
    significance = welch_t_test(bad_region_scores, good_region_scores)
    assert significance.significant is True

    for i, score in enumerate(good_region_scores):
        record_optimization_trial(
            log,
            subject_name="sma_cross",
            trial=OptimizationTrial(
                parameters={"fast": _TARGET_FAST, "run": i},
                in_sample_score=score,
                out_of_sample_score=score,
            ),
        )

    text = render_subject_report(log, "sma_cross", outcome_key="out_of_sample_score")
    assert "Runs: 8 total (7 carrying 'out_of_sample_score')" in text
    assert "mean=" in text
