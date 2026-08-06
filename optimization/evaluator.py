from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Evaluator(Protocol):
    """Scores one parameter set against a backtest run function the caller
    supplies (any Analytics Engine metric -- Sharpe, Sortino, profit factor,
    total return). The signature itself is the structural overfitting guard:
    it is not possible to implement this Protocol while returning only one
    score, so every optimizer trial always carries both -- there is no code
    path through this engine that produces a parameter ranking without an
    out-of-sample comparison.
    """

    def evaluate(self, parameters: dict[str, Any]) -> tuple[float, float]:
        """Returns (in_sample_score, out_of_sample_score)."""
        ...


__all__ = ["Evaluator"]
