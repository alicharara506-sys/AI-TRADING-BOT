from __future__ import annotations

from core.interfaces.types import Direction, Evidence, MarketContext, Timeframe
from quant.technical_analysis.momentum import compute_adx


class HigherTimeframeAlignmentModule:
    """Higher-timeframe trend confirmation: reads context.higher_timeframe_bars
    (populated by a caller that fetched multi-timeframe data -- see
    live_trading/multi_timeframe.py) for the configured `timeframe`, and
    votes with the direction of that timeframe's own ADX-confirmed trend.
    Reuses compute_adx (quant/technical_analysis/momentum.py) rather than
    inventing a separate trend measure, so "higher timeframe agrees" means
    exactly what AdxTrendModule already means on the primary timeframe,
    just evaluated one timeframe up.

    Feeds SignalFusion as one more vote, the same as every other
    AnalysisModule -- deliberately not a separate parallel gate/veto layer,
    so a lower-timeframe signal against the higher-timeframe trend isn't
    silently discarded, just weighed against it like any other disagreeing
    Evidence.
    """

    name = "higher_timeframe_alignment"

    def __init__(
        self, *, timeframe: Timeframe, adx_period: int = 14, trend_threshold: float = 25.0
    ) -> None:
        if adx_period < 2:
            raise ValueError("adx_period must be >= 2")
        if not 0.0 < trend_threshold < 100.0:
            raise ValueError("trend_threshold must be in (0.0, 100.0)")
        self._timeframe = timeframe
        self._adx_period = adx_period
        self._trend_threshold = trend_threshold

    def analyze(self, context: MarketContext) -> list[Evidence]:
        higher_bars = context.higher_timeframe_bars.get(self._timeframe)
        if not higher_bars:
            return []

        result = compute_adx(higher_bars, period=self._adx_period)
        if result is None:
            return []

        plus_di, minus_di, adx = result
        if adx < self._trend_threshold or plus_di == minus_di:
            return []

        confidence = min((adx - self._trend_threshold) / (100.0 - self._trend_threshold), 1.0)
        if confidence <= 0.0:
            return []

        direction = Direction.LONG if plus_di > minus_di else Direction.SHORT
        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={
                    "timeframe": self._timeframe.value,
                    "adx": adx,
                    "plus_di": plus_di,
                    "minus_di": minus_di,
                },
            )
        ]


__all__ = ["HigherTimeframeAlignmentModule"]
