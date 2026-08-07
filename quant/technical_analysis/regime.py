from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from core.interfaces.types import Bar
from quant.technical_analysis.volatility import compute_atr

VolatilityRegime = Literal["low", "normal", "high"]


def compute_volatility_regime(
    bars: Sequence[Bar],
    *,
    atr_period: int = 14,
    lookback: int = 100,
    low_percentile: float = 33.0,
    high_percentile: float = 67.0,
) -> VolatilityRegime | None:
    """Classifies the current bar's volatility relative to its own recent
    history: computes an ATR value at each of the last `lookback` points and
    ranks the most recent one among them. Deliberately a *relative*, purely
    factual read (this symbol's volatility right now vs. its own recent
    past) -- not a fabricated absolute "market regime" label, which is the
    exact kind of unsupported claim this project's decision_engine module
    already declines to produce (see decision_engine/report.py's docstring).
    Not an AnalysisModule: a volatility level isn't itself directional
    evidence, so it has nothing to vote into SignalFusion -- it's a context
    tag for other modules/the dashboard to consume.

    Uses a mid-rank percentile (ties split evenly) so a flat, constant-
    volatility series lands at the 50th percentile ("normal") rather than
    being pushed to "high" by a naive inclusive rank. None until there's
    enough history for the full lookback window.
    """
    if atr_period < 2:
        raise ValueError("atr_period must be >= 2")
    if lookback < 2:
        raise ValueError("lookback must be >= 2")
    if not 0.0 < low_percentile < high_percentile < 100.0:
        raise ValueError("low_percentile must be < high_percentile, both in (0.0, 100.0)")

    needed = lookback + atr_period
    if len(bars) < needed:
        return None

    atr_series: list[float] = []
    for end in range(len(bars) - lookback + 1, len(bars) + 1):
        atr = compute_atr(bars[:end], period=atr_period)
        if atr is None:
            return None
        atr_series.append(atr)

    current = atr_series[-1]
    below = sum(1 for value in atr_series if value < current)
    equal = sum(1 for value in atr_series if value == current)
    rank = (below + 0.5 * equal) / len(atr_series) * 100.0

    if rank <= low_percentile:
        return "low"
    if rank >= high_percentile:
        return "high"
    return "normal"


__all__ = ["VolatilityRegime", "compute_volatility_regime"]
