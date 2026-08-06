from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from core.interfaces.validation import CheckResult

_MIN_TRADES = 10


class MonteCarloCheck:
    """Bootstrap-resamples the trade-return sequence to build a distribution of
    possible equity curves and their max drawdowns, and fails when the tail-risk
    (e.g. 95th percentile) drawdown exceeds a configured limit -- reporting
    drawdown/ruin risk across many possible trade orderings rather than trusting
    the one historical sequence that happened to occur.
    """

    name = "monte_carlo_drawdown"

    def __init__(
        self,
        *,
        max_drawdown: float,
        iterations: int = 1000,
        percentile: float = 0.95,
        seed: int | None = None,
    ) -> None:
        if iterations < 100:
            raise ValueError("iterations must be >= 100 for a meaningful distribution")
        if max_drawdown <= 0:
            raise ValueError("max_drawdown must be > 0")
        if not 0.0 < percentile < 1.0:
            raise ValueError("percentile must be in (0, 1)")
        self._iterations = iterations
        self._max_drawdown = max_drawdown
        self._percentile = percentile
        self._seed = seed

    def run(self, trade_returns: Sequence[float]) -> CheckResult:
        if len(trade_returns) < _MIN_TRADES:
            return CheckResult(
                name=self.name,
                passed=False,
                detail={
                    "reason": f"fewer than {_MIN_TRADES} trades; "
                    "resampled distribution would be unreliable",
                    "trade_count": len(trade_returns),
                },
            )

        rng = np.random.default_rng(self._seed)
        returns = np.asarray(trade_returns, dtype=float)
        drawdowns = np.empty(self._iterations)

        for i in range(self._iterations):
            resampled = rng.choice(returns, size=len(returns), replace=True)
            equity_curve = np.cumsum(resampled)
            running_max = np.maximum.accumulate(equity_curve)
            drawdowns[i] = float((running_max - equity_curve).max())

        tail_drawdown = float(np.quantile(drawdowns, self._percentile))
        passed = tail_drawdown <= self._max_drawdown

        return CheckResult(
            name=self.name,
            passed=passed,
            detail={
                "tail_drawdown": tail_drawdown,
                "percentile": self._percentile,
                "max_drawdown_limit": self._max_drawdown,
                "iterations": self._iterations,
            },
        )


__all__ = ["MonteCarloCheck"]
