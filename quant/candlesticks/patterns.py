from __future__ import annotations

from core.interfaces.types import Direction, Evidence, MarketContext


class EngulfingPatternModule:
    """Bullish/Bearish Engulfing recognition: the current candle's real body
    fully contains the prior candle's real body, with opposite polarity.
    Confidence is scaled by how much larger the engulfing body is relative to
    the engulfed one -- a more decisive engulfment.

    Historical win-rate-based confidence (per the architecture's Analytics
    Engine lookup) is a later addition once that engine exists; this is
    geometry-only for now, an explicitly scoped simplification, not a
    placeholder pretending otherwise.
    """

    name = "engulfing_pattern"

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
        confidence = min(size_ratio - 1.0, 1.0)
        if confidence <= 0.0:
            return []

        evidence = Evidence(
            source_module=self.name,
            direction=direction,
            confidence=confidence,
            rationale={"pattern": "engulfing", "size_ratio": size_ratio},
            supporting_data={
                "previous_body": previous_body,
                "current_body": current_body,
            },
        )
        return [evidence]


__all__ = ["EngulfingPatternModule"]
