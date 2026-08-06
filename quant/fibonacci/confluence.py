from __future__ import annotations

from core.interfaces.types import Bar, Direction, Evidence, MarketContext

_RETRACEMENT_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)


def _find_last_swings(bars: list[Bar], *, arm: int) -> tuple[int | None, int | None]:
    """Fractal-style swing detection: a bar is a swing high/low if its high/low
    is the most extreme within `arm` bars on either side. Returns the index of
    the most recent confirmed swing low and swing high seen anywhere in `bars`.
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


class FibonacciConfluenceModule:
    """Automatic Fibonacci retracement confluence over the most recent impulse
    leg (the last confirmed swing low -> swing high, or high -> low). Emits
    Evidence when the current price sits within `tolerance` (as a fraction of
    the leg's range) of one of the standard retracement levels, with confidence
    scaled by proximity to that level. Multi-swing / multi-timeframe clustering
    (the fuller "confluence" breadth) is a later addition on top of this same
    single-leg mechanism.
    """

    name = "fibonacci_confluence"

    def __init__(self, *, swing_arm: int = 2, tolerance: float = 0.03) -> None:
        if swing_arm < 1:
            raise ValueError("swing_arm must be >= 1")
        if tolerance <= 0:
            raise ValueError("tolerance must be > 0")
        self._swing_arm = swing_arm
        self._tolerance = tolerance

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = list(context.bars)
        if len(bars) < 2 * self._swing_arm + 3:
            return []

        low_index, high_index = _find_last_swings(bars, arm=self._swing_arm)
        if low_index is None or high_index is None or low_index == high_index:
            return []

        impulse_up = low_index < high_index
        swing_low = bars[low_index].low
        swing_high = bars[high_index].high
        leg_range = swing_high - swing_low
        if leg_range <= 0:
            return []

        current = bars[-1].close
        best_ratio: float | None = None
        best_level: float | None = None
        best_distance: float | None = None
        for ratio in _RETRACEMENT_RATIOS:
            level = swing_high - ratio * leg_range if impulse_up else swing_low + ratio * leg_range
            distance = abs(current - level) / leg_range
            if best_distance is None or distance < best_distance:
                best_ratio, best_level, best_distance = ratio, level, distance

        if best_distance is None or best_distance > self._tolerance:
            return []

        # In an up-impulse, a pullback to a fib level suggests continuation LONG
        # (buying the dip); in a down-impulse, continuation SHORT.
        direction = Direction.LONG if impulse_up else Direction.SHORT
        confidence = max(0.0, 1.0 - best_distance / self._tolerance)
        if confidence <= 0.0:
            return []

        evidence = Evidence(
            source_module=self.name,
            direction=direction,
            confidence=confidence,
            rationale={
                "fib_ratio": best_ratio,
                "impulse_up": impulse_up,
                "distance_fraction_of_range": best_distance,
            },
            supporting_data={
                "swing_low": swing_low,
                "swing_high": swing_high,
                "level": best_level,
                "current": current,
            },
        )
        return [evidence]


__all__ = ["FibonacciConfluenceModule"]
