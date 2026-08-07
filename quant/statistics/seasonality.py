from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from core.interfaces.types import Bar, Direction, Evidence, MarketContext

GroupBy = Literal["weekday", "hour"]


def compute_seasonal_bias(
    bars: Sequence[Bar], *, group_by: GroupBy = "weekday"
) -> dict[int, tuple[float, int]]:
    """Mean bar-to-bar return and sample count, grouped by the closing bar's
    calendar weekday (0=Monday..6=Sunday) or hour-of-day (0-23) --  the
    entire "seasonality" claim this module makes: a real, checkable
    historical average conditioned on a real calendar bucket, nothing more.
    """
    if group_by not in ("weekday", "hour"):
        raise ValueError("group_by must be 'weekday' or 'hour'")

    buckets: dict[int, list[float]] = {}
    for previous, current in zip(bars, bars[1:], strict=False):
        if previous.close == 0:
            continue
        key = current.timestamp.weekday() if group_by == "weekday" else current.timestamp.hour
        buckets.setdefault(key, []).append((current.close - previous.close) / previous.close)

    return {key: (sum(values) / len(values), len(values)) for key, values in buckets.items()}


class SeasonalityModule:
    """Evidence from a calendar-bucket historical bias: only fires once the
    current bar's own weekday/hour bucket has at least `min_samples` prior
    observations (the same "don't vote on thin data" discipline
    HistoricalHitRateStore already enforces elsewhere) and the bucket's mean
    return clears `min_mean_return` -- otherwise a single noisy bucket could
    vote with unwarranted confidence. Confidence scales linearly up to
    `scale_return`, the mean-return magnitude treated as maximal conviction.
    """

    name = "seasonality"

    def __init__(
        self,
        *,
        group_by: GroupBy = "weekday",
        min_samples: int = 20,
        min_mean_return: float = 0.0005,
        scale_return: float = 0.01,
    ) -> None:
        if group_by not in ("weekday", "hour"):
            raise ValueError("group_by must be 'weekday' or 'hour'")
        if min_samples < 2:
            raise ValueError("min_samples must be >= 2")
        if min_mean_return < 0:
            raise ValueError("min_mean_return must be >= 0")
        if scale_return <= 0:
            raise ValueError("scale_return must be > 0")
        self._group_by: GroupBy = group_by
        self._min_samples = min_samples
        self._min_mean_return = min_mean_return
        self._scale_return = scale_return

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        if len(bars) < self._min_samples + 1:
            return []

        bias = compute_seasonal_bias(bars, group_by=self._group_by)
        current_bar = bars[-1]
        key = (
            current_bar.timestamp.weekday()
            if self._group_by == "weekday"
            else current_bar.timestamp.hour
        )
        entry = bias.get(key)
        if entry is None:
            return []

        mean_return, sample_count = entry
        if sample_count < self._min_samples or abs(mean_return) < self._min_mean_return:
            return []

        confidence = min(abs(mean_return) / self._scale_return, 1.0)
        if confidence <= 0.0:
            return []

        direction = Direction.LONG if mean_return > 0 else Direction.SHORT
        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={
                    "group_by": self._group_by,
                    "bucket": key,
                    "mean_return": mean_return,
                    "sample_count": sample_count,
                },
            )
        ]


__all__ = ["GroupBy", "SeasonalityModule", "compute_seasonal_bias"]
