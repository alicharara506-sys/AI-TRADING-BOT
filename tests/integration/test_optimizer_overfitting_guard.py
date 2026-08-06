from __future__ import annotations

from typing import Any

from optimization.algorithms.grid_search import GridSearchOptimizer


class _SyntheticStrategyEvaluator:
    """Simulates scoring an SMA-crossover-style strategy: very short fast
    periods fit in-sample noise well but fail to generalize (classic
    overfitting), while moderate periods perform consistently in both halves.
    """

    def evaluate(self, parameters: dict[str, Any]) -> tuple[float, float]:
        fast_period = parameters["fast_period"]
        if fast_period <= 3:
            return 100.0, 5.0  # overfit: great in-sample, collapses out-of-sample
        return 20.0, 18.0  # robust: consistent in both halves


def test_optimizer_rejects_the_overfit_parameter_set() -> None:
    """Phase 9's exit criteria: the overfitting guard actually changes which
    parameter set the engine recommends -- not just that the result type
    happens to carry both scores.
    """
    optimizer = GridSearchOptimizer({"fast_period": [2, 3, 10, 20]})
    result = optimizer.run(_SyntheticStrategyEvaluator())

    # Structural guarantee: every trial reports both scores.
    assert len(result.trials) == 4
    for trial in result.trials:
        assert trial.in_sample_score is not None
        assert trial.out_of_sample_score is not None

    # A naive "rank by in-sample score" optimizer would pick fast_period 2 or 3
    # (score 100). Ranking by out-of-sample score instead picks a robust one.
    best = result.best()
    assert best.parameters["fast_period"] in (10, 20)
    assert best.out_of_sample_score == 18.0

    # The explicit overfitting filter excludes the short-period trials outright.
    best_safe = result.best_within_degradation(max_degradation=0.3)
    assert best_safe.parameters["fast_period"] in (10, 20)

    overfit_trials = [trial for trial in result.trials if trial.parameters["fast_period"] <= 3]
    assert len(overfit_trials) == 2
    assert all(
        trial.degradation is not None and trial.degradation > 0.3 for trial in overfit_trials
    )
