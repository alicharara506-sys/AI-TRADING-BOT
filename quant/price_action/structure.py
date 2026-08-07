from __future__ import annotations

from collections.abc import Sequence

from core.interfaces.types import Bar, Direction, Evidence, MarketContext
from quant.price_action.swings import find_all_swing_points, find_last_swings

# Geometry-only confidence: historical win-rate-based confidence (per the
# architecture's Analytics Engine lookup) is a later addition once that
# engine exists to supply it. This is an explicitly scoped simplification,
# matching the same choice made in the Phase 7 candlestick module.
_CONFIDENCE = 0.7


class MarketStructureModule:
    """Break of Structure (BOS) / Change of Character (CHOCH), the core Smart
    Money Concepts market-structure primitives: an uptrend is a sequence of
    higher highs and higher lows, a downtrend the reverse. BOS fires when price
    breaks past the most recent swing level in the direction of the prevailing
    structure (continuation); CHOCH fires when price breaks the opposite way
    (a potential reversal). Reuses the shared swing-point sequence rather than
    its own detection logic.
    """

    name = "market_structure"

    def __init__(self, *, swing_arm: int = 2) -> None:
        if swing_arm < 1:
            raise ValueError("swing_arm must be >= 1")
        self._swing_arm = swing_arm

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = list(context.bars)
        points = find_all_swing_points(bars, arm=self._swing_arm)
        highs = [(index, bars[index].high) for index, kind in points if kind == "high"]
        lows = [(index, bars[index].low) for index, kind in points if kind == "low"]
        if len(highs) < 2 or len(lows) < 2:
            return []

        prev_high, last_high = highs[-2][1], highs[-1][1]
        prev_low, last_low = lows[-2][1], lows[-1][1]
        current = bars[-1].close

        uptrend = last_high > prev_high and last_low > prev_low
        downtrend = last_high < prev_high and last_low < prev_low

        if uptrend:
            if current > last_high:
                return [
                    self._evidence(Direction.LONG, "bos_uptrend_continuation", last_high, current)
                ]
            if current < last_low:
                return [
                    self._evidence(Direction.SHORT, "choch_uptrend_reversal", last_low, current)
                ]
        elif downtrend:
            if current < last_low:
                return [
                    self._evidence(
                        Direction.SHORT, "bos_downtrend_continuation", last_low, current
                    )
                ]
            if current > last_high:
                return [
                    self._evidence(
                        Direction.LONG, "choch_downtrend_reversal", last_high, current
                    )
                ]

        return []

    def _evidence(self, direction: Direction, event: str, level: float, current: float) -> Evidence:
        return Evidence(
            source_module=self.name,
            direction=direction,
            confidence=_CONFIDENCE,
            rationale={"event": event, "level": level, "current": current},
        )


def compute_structure_invalidation_level(
    bars: Sequence[Bar], direction: Direction, *, swing_arm: int = 2
) -> float | None:
    """The most recent confirmed swing low (for a LONG) or swing high (for a
    SHORT) -- the level whose break means the structural premise the trade
    was taken on (that swing held) is invalidated, as distinct from an
    ATR-based stop that's sized off volatility alone and may sit well
    inside or outside where the actual market structure would call it.
    Reuses the same swing-detection primitive Fibonacci confluence and
    this module's own BOS/CHOCH logic already use. None if no swing of the
    relevant kind has been confirmed yet, or `direction` is NEUTRAL (an
    invalidation level presupposes a directional trade).
    """
    low_index, high_index = find_last_swings(bars, arm=swing_arm)
    if direction is Direction.LONG:
        return bars[low_index].low if low_index is not None else None
    if direction is Direction.SHORT:
        return bars[high_index].high if high_index is not None else None
    return None


__all__ = ["MarketStructureModule", "compute_structure_invalidation_level"]
