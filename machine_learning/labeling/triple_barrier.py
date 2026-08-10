from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass

from core.interfaces.types import Bar
from quant.technical_analysis.volatility import compute_atr


class BarrierHit(enum.Enum):
    UPPER = "upper"
    LOWER = "lower"
    HORIZONTAL = "horizontal"


@dataclass(frozen=True, slots=True)
class TripleBarrierLabel:
    label: int  # +1 (upper hit), -1 (lower hit), 0 (neither -- horizontal/time barrier)
    barrier_hit: BarrierHit
    bars_to_hit: int
    return_pct: float


def label_triple_barrier(
    bars: Sequence[Bar],
    *,
    entry_index: int,
    atr_period: int = 14,
    upper_multiple: float = 1.5,
    lower_multiple: float = 1.5,
    horizon: int = 20,
) -> TripleBarrierLabel | None:
    """The Triple Barrier Method (Lopez de Prado): from `entry_index`, walk
    forward up to `horizon` bars and label the outcome by whichever of
    three barriers is touched first -- an upper barrier at
    entry_price + upper_multiple*ATR (label +1), a lower barrier at
    entry_price - lower_multiple*ATR (label -1), or neither touched within
    `horizon` bars (the horizontal/time barrier: label 0). Pure price-and-
    ATR arithmetic, no external labeling library.

    None when there isn't enough history at entry_index to compute ATR, or
    fewer than `horizon` bars remain after it -- a full, untruncated horizon
    is required rather than silently scoring off however many bars happen
    to remain, since a short partial window would bias labels near the end
    of a history towards whichever barrier happened to be closer.
    """
    if atr_period < 2:
        raise ValueError("atr_period must be >= 2")
    if upper_multiple <= 0 or lower_multiple <= 0:
        raise ValueError("upper_multiple and lower_multiple must be > 0")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if not 0 <= entry_index < len(bars):
        raise ValueError("entry_index out of range")
    if entry_index + horizon >= len(bars):
        return None

    atr = compute_atr(bars[: entry_index + 1], period=atr_period)
    if atr is None or atr <= 0:
        return None

    entry_price = bars[entry_index].close
    upper = entry_price + upper_multiple * atr
    lower = entry_price - lower_multiple * atr

    for offset in range(1, horizon + 1):
        bar = bars[entry_index + offset]
        hit_upper = bar.high >= upper
        hit_lower = bar.low <= lower
        if hit_upper and hit_lower:
            # Both barriers touched within the same bar (a wide-range bar):
            # resolve towards whichever barrier the bar's open sat closer
            # to, an explicit, documented tie-break rather than an
            # arbitrary "upper always wins" default.
            if abs(bar.open - upper) <= abs(bar.open - lower):
                hit_upper, hit_lower = True, False
            else:
                hit_upper, hit_lower = False, True
        if hit_upper:
            return TripleBarrierLabel(
                label=1,
                barrier_hit=BarrierHit.UPPER,
                bars_to_hit=offset,
                return_pct=(upper - entry_price) / entry_price,
            )
        if hit_lower:
            return TripleBarrierLabel(
                label=-1,
                barrier_hit=BarrierHit.LOWER,
                bars_to_hit=offset,
                return_pct=(lower - entry_price) / entry_price,
            )

    final_bar = bars[entry_index + horizon]
    return TripleBarrierLabel(
        label=0,
        barrier_hit=BarrierHit.HORIZONTAL,
        bars_to_hit=horizon,
        return_pct=(final_bar.close - entry_price) / entry_price,
    )


def build_training_labels(
    bars: Sequence[Bar],
    *,
    atr_period: int = 14,
    upper_multiple: float = 1.5,
    lower_multiple: float = 1.5,
    horizon: int = 20,
) -> list[tuple[int, TripleBarrierLabel]]:
    """Every (entry_index, label) pair label_triple_barrier can produce
    across the full `bars` history -- the bulk training-label builder
    RuleForest trains on, so its own training loop doesn't need to know
    triple-barrier's own bounds-checking rules."""
    labels: list[tuple[int, TripleBarrierLabel]] = []
    for entry_index in range(len(bars)):
        label = label_triple_barrier(
            bars,
            entry_index=entry_index,
            atr_period=atr_period,
            upper_multiple=upper_multiple,
            lower_multiple=lower_multiple,
            horizon=horizon,
        )
        if label is not None:
            labels.append((entry_index, label))
    return labels


__all__ = ["BarrierHit", "TripleBarrierLabel", "build_training_labels", "label_triple_barrier"]
