from __future__ import annotations

from analytics.hit_rate_store import HistoricalHitRateStore
from core.interfaces.types import Direction, Evidence, MarketContext


class EngulfingPatternModule:
    """Bullish/Bearish Engulfing recognition: the current candle's real body
    fully contains the prior candle's real body, with opposite polarity.

    Confidence comes from the Analytics Engine's historical hit rate for this
    exact pattern/symbol once enough history exists (a HistoricalHitRateStore
    is supplied and has recorded at least its minimum sample count) -- real
    backtested performance, not a fixed textbook figure. Until then, or when
    no store is supplied at all, confidence falls back to the geometric
    signal alone (how much larger the engulfing body is than the engulfed
    one), preserving this module's original behavior exactly.
    """

    name = "engulfing_pattern"

    def __init__(self, *, hit_rate_store: HistoricalHitRateStore | None = None) -> None:
        self._hit_rate_store = hit_rate_store

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        if len(bars) < 2:
            return []

        previous, current = bars[-2], bars[-1]
        previous_body_low = min(previous.open, previous.close)
        previous_body_high = max(previous.open, previous.close)
        current_body_low = min(current.open, current.close)
        current_body_high = max(current.open, current.close)

        previous_body = previous_body_high - previous_body_low
        current_body = current_body_high - current_body_low
        if previous_body <= 0 or current_body <= 0:
            return []

        engulfs = current_body_low <= previous_body_low and current_body_high >= previous_body_high
        if not engulfs:
            return []

        previous_bearish = previous.close < previous.open
        current_bullish = current.close > current.open
        previous_bullish = previous.close > previous.open
        current_bearish = current.close < current.open

        if previous_bearish and current_bullish:
            direction = Direction.LONG
        elif previous_bullish and current_bearish:
            direction = Direction.SHORT
        else:
            return []

        size_ratio = current_body / previous_body
        geometric_confidence = min(size_ratio - 1.0, 1.0)
        if geometric_confidence <= 0.0:
            return []

        confidence = geometric_confidence
        confidence_source = "geometric"
        if self._hit_rate_store is not None:
            historical = self._hit_rate_store.hit_rate(self.name, context.symbol.canonical)
            if historical is not None:
                confidence = historical
                confidence_source = "historical_hit_rate"

        evidence = Evidence(
            source_module=self.name,
            direction=direction,
            confidence=confidence,
            rationale={
                "pattern": "engulfing",
                "size_ratio": size_ratio,
                "confidence_source": confidence_source,
            },
            supporting_data={
                "previous_body": previous_body,
                "current_body": current_body,
                "geometric_confidence": geometric_confidence,
            },
        )
        return [evidence]


__all__ = ["EngulfingPatternModule"]
