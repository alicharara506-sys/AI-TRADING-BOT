from __future__ import annotations

from collections.abc import Sequence

from core.interfaces.types import Bar, Direction, Evidence, MarketContext
from quant.price_action.swings import find_last_swings
from quant.technical_analysis.volatility import compute_atr


def _typical_price(bar: Bar) -> float:
    return (bar.high + bar.low + bar.close) / 3.0


def compute_vwap(bars: Sequence[Bar], *, period: int) -> float | None:
    """Volume-weighted average price over the last `period` bars, using each
    bar's typical price (H+L+C)/3 -- the standard VWAP definition. None
    until there's enough history, or if the window's total volume is zero
    (MT5 forex/CFD tick volume can legitimately be zero on an illiquid
    symbol/timeframe combination).
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(bars) < period:
        return None
    return _weighted_average_price(bars[-period:])


def compute_anchored_vwap(bars: Sequence[Bar], *, anchor_index: int) -> float | None:
    """VWAP computed from `anchor_index` through the end of `bars` -- the
    same volume-weighted average as compute_vwap, just anchored to a
    specific bar (a swing point, a session open) instead of a trailing
    window.
    """
    if not 0 <= anchor_index < len(bars):
        raise ValueError("anchor_index out of range")
    return _weighted_average_price(bars[anchor_index:])


def _weighted_average_price(window: Sequence[Bar]) -> float | None:
    total_volume = sum(bar.volume for bar in window)
    if total_volume <= 0:
        return None
    weighted_sum = sum(_typical_price(bar) * bar.volume for bar in window)
    return weighted_sum / total_volume


class AnchoredVwapModule:
    """Anchored VWAP trend-confirmation: anchors at the most recent confirmed
    swing point (reusing the same shared swing-detection primitive Fibonacci
    confluence and market structure already use) and reads price trading
    above/below that anchored VWAP as evidence of bullish/bearish control --
    the standard institutional read of VWAP, distinct from a simple moving
    average. Confidence is the distance from VWAP scaled by ATR, since a raw
    price-VWAP distance has no natural bound of its own.
    """

    name = "anchored_vwap"

    def __init__(self, *, swing_arm: int = 2, atr_period: int = 14) -> None:
        if swing_arm < 1:
            raise ValueError("swing_arm must be >= 1")
        if atr_period < 2:
            raise ValueError("atr_period must be >= 2")
        self._swing_arm = swing_arm
        self._atr_period = atr_period

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        if len(bars) < 2 * self._swing_arm + 3:
            return []

        low_index, high_index = find_last_swings(bars, arm=self._swing_arm)
        if low_index is None or high_index is None:
            return []
        anchor_index = max(low_index, high_index)

        vwap = compute_anchored_vwap(bars, anchor_index=anchor_index)
        if vwap is None:
            return []

        atr = compute_atr(bars, period=self._atr_period)
        if atr is None or atr <= 0:
            return []

        current = bars[-1].close
        distance = current - vwap
        if distance == 0:
            return []

        confidence = min(abs(distance) / atr, 1.0)
        if confidence <= 0.0:
            return []

        direction = Direction.LONG if distance > 0 else Direction.SHORT
        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={"vwap": vwap, "anchor_index": anchor_index, "current": current},
            )
        ]


__all__ = ["AnchoredVwapModule", "compute_anchored_vwap", "compute_vwap"]
