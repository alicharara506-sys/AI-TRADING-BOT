from __future__ import annotations

from collections.abc import Sequence

from core.interfaces.validation import CheckResult

_MIN_TRADES = 10


class WalkForwardCheck:
    """Splits a chronologically-ordered trade-return series into an in-sample
    and out-of-sample half, and fails when out-of-sample performance degrades
    beyond a configured tolerance relative to in-sample -- the walk-forward
    signature of a strategy whose apparent edge doesn't survive out of sample.
    """

    name = "walk_forward"

    def __init__(self, *, max_degradation: float = 0.5) -> None:
        if not 0.0 <= max_degradation <= 1.0:
            raise ValueError("max_degradation must be in [0, 1]")
        self._max_degradation = max_degradation

    def run(self, trade_returns: Sequence[float]) -> CheckResult:
        if len(trade_returns) < _MIN_TRADES:
            return CheckResult(
                name=self.name,
                passed=False,
                detail={
                    "reason": f"fewer than {_MIN_TRADES} trades; "
                    "cannot walk-forward split meaningfully",
                    "trade_count": len(trade_returns),
                },
            )

        midpoint = len(trade_returns) // 2
        in_sample_total = sum(trade_returns[:midpoint])
        out_of_sample_total = sum(trade_returns[midpoint:])

        if in_sample_total <= 0:
            # Nothing to degrade from -- the in-sample half itself wasn't
            # profitable, so out-of-sample only needs to not be worse.
            passed = out_of_sample_total >= in_sample_total
            degradation = None
        else:
            degradation = 1.0 - (out_of_sample_total / in_sample_total)
            passed = degradation <= self._max_degradation

        return CheckResult(
            name=self.name,
            passed=passed,
            detail={
                "in_sample_total_return": in_sample_total,
                "out_of_sample_total_return": out_of_sample_total,
                "degradation": degradation,
                "max_degradation": self._max_degradation,
            },
        )


__all__ = ["WalkForwardCheck"]
