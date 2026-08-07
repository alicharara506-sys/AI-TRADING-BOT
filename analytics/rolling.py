from __future__ import annotations

from collections.abc import Callable, Sequence


def compute_rolling_metric(
    returns: Sequence[float], *, window: int, metric_fn: Callable[[Sequence[float]], float]
) -> list[float]:
    """Applies `metric_fn` (any analytics/metrics.py function -- Sharpe,
    max drawdown, profit factor, whatever) to every `window`-wide sliding
    slice of `returns`, oldest window first. A generic wrapper rather than
    a rolling variant of each metric individually, so there is exactly one
    rolling-window implementation, not one per metric. Returns an empty
    list when there isn't yet a full window's worth of returns -- the same
    "no result rather than a guess from partial data" pattern used
    throughout this platform.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if len(returns) < window:
        return []
    return [metric_fn(returns[i : i + window]) for i in range(len(returns) - window + 1)]


__all__ = ["compute_rolling_metric"]
