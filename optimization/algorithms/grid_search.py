from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from typing import Any

from optimization.evaluator import Evaluator
from optimization.result import OptimizationResult, OptimizationTrial


class GridSearchOptimizer:
    """Exhaustive cartesian-product search over a discrete parameter grid --
    the simplest optimizer, and the cheapest to validate the overfitting guard
    against before layering Bayesian/genetic/PSO on top.
    """

    def __init__(self, parameter_grid: Mapping[str, Sequence[Any]]) -> None:
        if not parameter_grid:
            raise ValueError("parameter_grid must not be empty")
        for name, values in parameter_grid.items():
            if len(values) == 0:
                raise ValueError(f"parameter '{name}' has no candidate values")
        self._parameter_grid = {name: tuple(values) for name, values in parameter_grid.items()}

    def candidates(self) -> list[dict[str, Any]]:
        names = list(self._parameter_grid)
        value_lists = [self._parameter_grid[name] for name in names]
        return [dict(zip(names, combo, strict=True)) for combo in itertools.product(*value_lists)]

    def run(self, evaluator: Evaluator) -> OptimizationResult:
        trials = []
        for parameters in self.candidates():
            in_sample, out_of_sample = evaluator.evaluate(parameters)
            trials.append(
                OptimizationTrial(
                    parameters=parameters,
                    in_sample_score=in_sample,
                    out_of_sample_score=out_of_sample,
                )
            )
        return OptimizationResult(trials=tuple(trials))


__all__ = ["GridSearchOptimizer"]
