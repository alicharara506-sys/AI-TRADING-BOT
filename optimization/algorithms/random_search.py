from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from optimization.evaluator import Evaluator
from optimization.result import OptimizationResult, OptimizationTrial


class RandomSearchOptimizer:
    """Uniform-random sampling over continuous parameter ranges. Seeded for
    reproducibility -- two runs with the same seed explore the identical
    sequence of candidates, which matters for reproducible research, not just
    for tests.
    """

    def __init__(
        self,
        parameter_ranges: Mapping[str, tuple[float, float]],
        *,
        iterations: int,
        seed: int | None = None,
    ) -> None:
        if not parameter_ranges:
            raise ValueError("parameter_ranges must not be empty")
        for name, (low, high) in parameter_ranges.items():
            if low >= high:
                raise ValueError(f"parameter '{name}' range must have low < high")
        if iterations < 1:
            raise ValueError("iterations must be >= 1")
        self._parameter_ranges = dict(parameter_ranges)
        self._iterations = iterations
        self._seed = seed

    def run(self, evaluator: Evaluator) -> OptimizationResult:
        rng = np.random.default_rng(self._seed)
        trials = []
        for _ in range(self._iterations):
            parameters = {
                name: float(rng.uniform(low, high))
                for name, (low, high) in self._parameter_ranges.items()
            }
            in_sample, out_of_sample = evaluator.evaluate(parameters)
            trials.append(
                OptimizationTrial(
                    parameters=parameters,
                    in_sample_score=in_sample,
                    out_of_sample_score=out_of_sample,
                )
            )
        return OptimizationResult(trials=tuple(trials))


__all__ = ["RandomSearchOptimizer"]
