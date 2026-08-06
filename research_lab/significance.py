from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from scipy import stats


@dataclass(frozen=True, slots=True)
class SignificanceResult:
    statistic: float
    p_value: float
    significant: bool
    alpha: float


def welch_t_test(
    baseline: Sequence[float], candidate: Sequence[float], *, alpha: float = 0.05
) -> SignificanceResult:
    """Welch's two-sample t-test: does candidate's mean differ from
    baseline's without assuming equal variance (the two samples being
    compared -- e.g. two strategies' per-trade returns, or two parameter
    sets' out-of-sample scores across repeated trials -- have no reason to
    share a variance). Answers "is this difference real, or noise" for an
    experiment comparison, which nothing in the platform computed before
    this module existed.
    """
    if len(baseline) < 2 or len(candidate) < 2:
        raise ValueError("each sample needs at least 2 observations for a t-test")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be in (0, 1)")

    result = stats.ttest_ind(candidate, baseline, equal_var=False)
    p_value = float(result.pvalue)
    return SignificanceResult(
        statistic=float(result.statistic),
        p_value=p_value,
        significant=p_value < alpha,
        alpha=alpha,
    )


__all__ = ["SignificanceResult", "welch_t_test"]
