from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OptimizationTrial:
    """One parameter set's result: both scores are always present (the
    Evaluator Protocol makes that structural), so degradation is always
    computable, not an optional afterthought.
    """

    parameters: dict[str, Any]
    in_sample_score: float
    out_of_sample_score: float

    @property
    def degradation(self) -> float | None:
        """Fraction of in-sample score lost out of sample. None when the
        in-sample score itself was non-positive -- there is nothing to degrade
        from a baseline of zero or negative.
        """
        if self.in_sample_score <= 0:
            return None
        return 1.0 - (self.out_of_sample_score / self.in_sample_score)


def _out_of_sample_score(trial: OptimizationTrial) -> float:
    return trial.out_of_sample_score


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    trials: tuple[OptimizationTrial, ...]

    def ranked(
        self, *, key: Callable[[OptimizationTrial], float] = _out_of_sample_score
    ) -> list[OptimizationTrial]:
        return sorted(self.trials, key=key, reverse=True)

    def best(
        self, *, key: Callable[[OptimizationTrial], float] = _out_of_sample_score
    ) -> OptimizationTrial:
        """Ranks by out-of-sample score by default -- never in-sample -- so
        picking "the best" never means picking the most overfit trial.
        """
        if not self.trials:
            raise ValueError("no trials to select from")
        return max(self.trials, key=key)

    def best_within_degradation(self, max_degradation: float) -> OptimizationTrial:
        """The explicit overfitting filter: only considers trials whose
        degradation is within tolerance (or undefined, meaning the in-sample
        half wasn't profitable to begin with) before ranking by out-of-sample
        score. Raises when every trial was rejected as overfit -- there is no
        silent fallback to an overfit "best".
        """
        candidates = [
            trial
            for trial in self.trials
            if trial.degradation is None or trial.degradation <= max_degradation
        ]
        if not candidates:
            raise ValueError(
                f"all {len(self.trials)} trial(s) exceeded max_degradation={max_degradation}; "
                "no non-overfit parameter set available"
            )
        return max(candidates, key=_out_of_sample_score)


__all__ = ["OptimizationResult", "OptimizationTrial"]
