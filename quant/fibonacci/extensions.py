from __future__ import annotations

from core.interfaces.types import Direction, Evidence, MarketContext
from quant.price_action.swings import find_last_swings

_EXTENSION_RATIOS = (1.272, 1.414, 1.618, 2.0, 2.618, 3.618, 4.236)


def compute_fibonacci_extensions(
    swing_low: float, swing_high: float, *, impulse_up: bool
) -> dict[float, float]:
    """Projects the standard extension ratios beyond a single impulse leg,
    using the same convention FibonacciConfluenceModule already uses for
    retracements (levels measured from the leg's opposite end): ratio=1.0
    is exactly the swing itself, ratio=1.618 is a point 61.8% of the leg's
    own length beyond it -- the standard single-leg Fibonacci extension/
    projection used for continuation targets, as distinct from a
    retracement (which projects *inside* the leg, for a pullback entry).
    """
    if swing_high <= swing_low:
        raise ValueError("swing_high must exceed swing_low")

    leg_range = swing_high - swing_low
    if impulse_up:
        return {ratio: swing_low + ratio * leg_range for ratio in _EXTENSION_RATIOS}
    return {ratio: swing_high - ratio * leg_range for ratio in _EXTENSION_RATIOS}


class FibonacciExtensionModule:
    """Continuation targets beyond the most recent impulse leg: when price
    trades near one of the standard extension ratios (1.272-4.236) projected
    beyond the swing, that's evidence of continuation in the impulse's own
    direction -- the mirror image of FibonacciConfluenceModule's pullback
    read, using the same swing-detection primitive and the same tolerance-
    based proximity confidence.
    """

    name = "fibonacci_extension"

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
        if swing_high <= swing_low:
            return []

        leg_range = swing_high - swing_low
        levels = compute_fibonacci_extensions(swing_low, swing_high, impulse_up=impulse_up)
        current = bars[-1].close

        best_ratio: float | None = None
        best_level: float | None = None
        best_distance: float | None = None
        for ratio, level in levels.items():
            distance = abs(current - level) / leg_range
            if best_distance is None or distance < best_distance:
                best_ratio, best_level, best_distance = ratio, level, distance

        if best_distance is None or best_distance > self._tolerance:
            return []

        direction = Direction.LONG if impulse_up else Direction.SHORT
        confidence = max(0.0, 1.0 - best_distance / self._tolerance)
        if confidence <= 0.0:
            return []

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={
                    "extension_ratio": best_ratio,
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
        ]


__all__ = ["FibonacciExtensionModule", "compute_fibonacci_extensions"]
