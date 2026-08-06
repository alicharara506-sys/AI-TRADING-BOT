from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from core.interfaces.types import Bar

SwingKind = Literal["high", "low"]


def find_last_swings(bars: Sequence[Bar], *, arm: int) -> tuple[int | None, int | None]:
    """Fractal-style swing detection: a bar is a swing high/low if its high/low
    is the most extreme within `arm` bars on either side. Returns the index of
    the most recent confirmed swing low and swing high seen anywhere in `bars`.

    Shared by every module that needs "the last significant turning points"
    (Fibonacci confluence, market structure, and future chart/harmonic pattern
    modules) so there is exactly one swing-detection implementation, not one
    reimplemented per module.

    On tied values (e.g. a perfectly flat run of prices) every bar in the tie
    satisfies "the extreme within its window", so this returns the last tied
    index rather than None -- callers that need to reject a degenerate
    (zero-range) result do so themselves, as Fibonacci confluence already does.
    """
    last_swing_low: int | None = None
    last_swing_high: int | None = None
    n = len(bars)
    for i in range(arm, n - arm):
        window = bars[i - arm : i + arm + 1]
        if bars[i].high == max(b.high for b in window):
            last_swing_high = i
        if bars[i].low == min(b.low for b in window):
            last_swing_low = i
    return last_swing_low, last_swing_high


def find_all_swing_points(bars: Sequence[Bar], *, arm: int) -> list[tuple[int, SwingKind]]:
    """Every confirmed swing point in chronological order, each tagged 'high' or
    'low'. Needed by anything that reasons about a *sequence* of turning points
    (e.g. higher-highs/higher-lows market structure), not just the single most
    recent low/high pair that find_last_swings returns.
    """
    points: list[tuple[int, SwingKind]] = []
    n = len(bars)
    for i in range(arm, n - arm):
        window = bars[i - arm : i + arm + 1]
        if bars[i].high == max(b.high for b in window):
            points.append((i, "high"))
        if bars[i].low == min(b.low for b in window):
            points.append((i, "low"))
    return points


__all__ = ["SwingKind", "find_all_swing_points", "find_last_swings"]
