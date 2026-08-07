"""Cross-symbol correlation: a pure computation over multiple symbols' bar
series, not an AnalysisModule -- AnalysisModule.analyze(context) only ever
sees a single symbol's MarketContext, so a genuinely multi-symbol
calculation like this has nothing to plug into SignalFusion directly. It's
a risk-engine input (correlated positions compound risk instead of
diversifying it) for a later phase, exposed here as the real, tested
building block that phase will consume.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from core.interfaces.types import Bar


def _pearson_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    covariance: float = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y, strict=True))
    variance_x: float = sum((xi - mean_x) ** 2 for xi in x)
    variance_y: float = sum((yi - mean_y) ** 2 for yi in y)
    denominator = math.sqrt(variance_x * variance_y)
    if denominator == 0:
        return 0.0
    return covariance / denominator


def compute_correlation_matrix(
    symbol_bars: Mapping[str, Sequence[Bar]], *, min_samples: int = 20
) -> dict[str, dict[str, float]] | None:
    """Pearson correlation of returns between every pair of symbols in
    `symbol_bars`, aligned on timestamps every symbol shares in common
    (different symbols can legitimately have gaps or different history
    lengths, so index-position alignment alone would silently misalign
    bars). None if fewer than 2 symbols are given, or if the shared-
    timestamp history is shorter than `min_samples` returns.
    """
    if len(symbol_bars) < 2:
        raise ValueError("need at least 2 symbols to compute a correlation matrix")
    if min_samples < 2:
        raise ValueError("min_samples must be >= 2")

    common_timestamps = None
    for bars in symbol_bars.values():
        timestamps = {bar.timestamp for bar in bars}
        common_timestamps = (
            timestamps if common_timestamps is None else common_timestamps & timestamps
        )
    if common_timestamps is None or len(common_timestamps) < min_samples + 1:
        return None

    sorted_timestamps = sorted(common_timestamps)
    returns: dict[str, list[float]] = {}
    for symbol, bars in symbol_bars.items():
        close_by_timestamp = {bar.timestamp: bar.close for bar in bars}
        closes = [close_by_timestamp[timestamp] for timestamp in sorted_timestamps]
        returns[symbol] = [
            (current - previous) / previous
            for previous, current in zip(closes, closes[1:], strict=False)
            if previous != 0
        ]

    if any(len(series) < min_samples for series in returns.values()):
        return None

    symbols = list(symbol_bars)
    return {
        row_symbol: {
            col_symbol: (
                1.0
                if row_symbol == col_symbol
                else _pearson_correlation(returns[row_symbol], returns[col_symbol])
            )
            for col_symbol in symbols
        }
        for row_symbol in symbols
    }


__all__ = ["compute_correlation_matrix"]
