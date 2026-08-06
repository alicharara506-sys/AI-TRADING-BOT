from __future__ import annotations

from typing import Any

import pytest

from optimization.algorithms.grid_search import GridSearchOptimizer


class _RecordingEvaluator:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def evaluate(self, parameters: dict[str, Any]) -> tuple[float, float]:
        self.calls.append(parameters)
        # A deterministic score derived from the parameters, just to have
        # something to assert on.
        score = float(sum(v for v in parameters.values() if isinstance(v, int | float)))
        return score, score


def test_rejects_empty_parameter_grid() -> None:
    with pytest.raises(ValueError):
        GridSearchOptimizer({})


def test_rejects_parameter_with_no_candidate_values() -> None:
    with pytest.raises(ValueError):
        GridSearchOptimizer({"fast_period": []})


def test_candidates_produces_full_cartesian_product() -> None:
    optimizer = GridSearchOptimizer({"fast_period": [5, 10], "slow_period": [20, 30, 40]})

    candidates = optimizer.candidates()

    assert len(candidates) == 6
    assert {"fast_period": 5, "slow_period": 20} in candidates
    assert {"fast_period": 10, "slow_period": 40} in candidates


def test_run_evaluates_every_candidate_exactly_once() -> None:
    optimizer = GridSearchOptimizer({"fast_period": [5, 10], "slow_period": [20, 30]})
    evaluator = _RecordingEvaluator()

    result = optimizer.run(evaluator)

    assert len(evaluator.calls) == 4
    assert len(result.trials) == 4
    for trial in result.trials:
        assert trial.in_sample_score == trial.out_of_sample_score
