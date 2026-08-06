from __future__ import annotations

from core.interfaces.types import Direction, Evidence, MarketContext
from quant.price_action.swings import find_last_swings

_RETRACEMENT_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)


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

        low_index, high_index = find_last_swings(bars, arm=self._swing_arm)
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
