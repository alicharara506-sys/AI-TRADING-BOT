from __future__ import annotations

from core.interfaces.types import Direction, Evidence, MarketContext


class OnBalanceVolumeModule:
    """On-Balance Volume trend confirmation/divergence: OBV rising while price
    also rises (or OBV falling while price falls) confirms the move is backed
    by volume; a divergence between price direction and OBV direction is
    evidence the move lacks conviction and may reverse.
    """

    name = "on_balance_volume"

    def __init__(self, *, lookback: int = 10) -> None:
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        self._lookback = lookback

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        if len(bars) < self._lookback + 1:
            return []

        window = bars[-(self._lookback + 1) :]
        obv = 0.0
        obv_start = 0.0
        for previous, current in zip(window, window[1:], strict=False):
            if current.close > previous.close:
                obv += current.volume
            elif current.close < previous.close:
                obv -= current.volume

        price_change = window[-1].close - window[0].close
        obv_change = obv - obv_start
        if price_change == 0 or obv_change == 0:
            return []

        price_up = price_change > 0
        obv_up = obv_change > 0

        if price_up == obv_up:
            direction = Direction.LONG if price_up else Direction.SHORT
            event = "obv_confirms_trend"
        else:
            direction = Direction.SHORT if price_up else Direction.LONG
            event = "obv_diverges_from_price"

        total_volume = sum(bar.volume for bar in window[1:])
        if total_volume <= 0:
            return []
        confidence = min(abs(obv_change) / total_volume, 1.0)
        if confidence <= 0.0:
            return []

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={
                    "event": event,
                    "price_change": price_change,
                    "obv_change": obv_change,
                },
            )
        ]


__all__ = ["OnBalanceVolumeModule"]
