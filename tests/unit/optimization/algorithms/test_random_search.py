from __future__ import annotations

from typing import Any

import pytest

from optimization.algorithms.random_search import RandomSearchOptimizer


class _RecordingEvaluator:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def evaluate(self, parameters: dict[str, Any]) -> tuple[float, float]:
        self.calls.append(parameters)
        return 1.0, 1.0


def test_rejects_empty_parameter_ranges() -> None:
    with pytest.raises(ValueError):
        RandomSearchOptimizer({}, iterations=10)


def test_rejects_invalid_range() -> None:
    with pytest.raises(ValueError):
        RandomSearchOptimizer({"fast_period": (10.0, 5.0)}, iterations=10)


def test_rejects_non_positive_iterations() -> None:
    with pytest.raises(ValueError):
        RandomSearchOptimizer({"fast_period": (5.0, 10.0)}, iterations=0)


def test_run_produces_the_requested_number_of_trials() -> None:
    optimizer = RandomSearchOptimizer({"fast_period": (5.0, 10.0)}, iterations=25, seed=1)
    evaluator = _RecordingEvaluator()

    result = optimizer.run(evaluator)

    assert len(result.trials) == 25
    assert len(evaluator.calls) == 25


def test_sampled_values_stay_within_configured_range() -> None:
    optimizer = RandomSearchOptimizer(
        {"fast_period": (5.0, 10.0), "slow_period": (20.0, 40.0)}, iterations=50, seed=1
    )
    evaluator = _RecordingEvaluator()

    optimizer.run(evaluator)

    for call in evaluator.calls:
        assert 5.0 <= call["fast_period"] <= 10.0
        assert 20.0 <= call["slow_period"] <= 40.0


def test_same_seed_produces_identical_candidate_sequence() -> None:
    evaluator_a = _RecordingEvaluator()
    evaluator_b = _RecordingEvaluator()

    RandomSearchOptimizer({"fast_period": (5.0, 10.0)}, iterations=10, seed=42).run(evaluator_a)
    RandomSearchOptimizer({"fast_period": (5.0, 10.0)}, iterations=10, seed=42).run(evaluator_b)

    assert evaluator_a.calls == evaluator_b.calls


def test_different_seeds_produce_different_sequences() -> None:
    evaluator_a = _RecordingEvaluator()
    evaluator_b = _RecordingEvaluator()

    RandomSearchOptimizer({"fast_period": (5.0, 10.0)}, iterations=10, seed=1).run(evaluator_a)
    RandomSearchOptimizer({"fast_period": (5.0, 10.0)}, iterations=10, seed=2).run(evaluator_b)

    assert evaluator_a.calls != evaluator_b.calls
