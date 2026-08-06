from __future__ import annotations

from core.interfaces.types import Direction, Evidence, MarketContext


class AtrVolatilityBreakoutModule:
    """Volatility breakout: when a bar's true range meaningfully exceeds the
    recent Average True Range, that expansion is evidence of a breakout in the
    direction the bar closed -- a common price-action volatility trigger, and
    the Technical Analysis Laboratory's volatility-category counterpart to the
    trend/momentum indicators built in Phase 2.
    """

    name = "atr_volatility_breakout"

    def __init__(self, *, period: int = 14, expansion_multiple: float = 1.5) -> None:
        if period < 2:
            raise ValueError("period must be >= 2")
        if expansion_multiple <= 1.0:
            raise ValueError("expansion_multiple must be > 1.0")
        self._period = period
        self._expansion_multiple = expansion_multiple

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        if len(bars) < self._period + 1:
            return []

        window = bars[-(self._period + 1) :]
        true_ranges = [
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
            for previous, current in zip(window, window[1:], strict=False)
        ]

        atr = sum(true_ranges[:-1]) / len(true_ranges[:-1])
        latest_true_range = true_ranges[-1]
        if atr <= 0 or latest_true_range < atr * self._expansion_multiple:
            return []

        latest_bar = window[-1]
        if latest_bar.close == latest_bar.open:
            return []
        direction = Direction.LONG if latest_bar.close > latest_bar.open else Direction.SHORT

        expansion_ratio = latest_true_range / atr
        confidence = min((expansion_ratio - 1.0) / self._expansion_multiple, 1.0)
        if confidence <= 0.0:
            return []

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={
                    "atr": atr,
                    "true_range": latest_true_range,
                    "expansion_ratio": expansion_ratio,
                },
            )
        ]


__all__ = ["AtrVolatilityBreakoutModule"]
