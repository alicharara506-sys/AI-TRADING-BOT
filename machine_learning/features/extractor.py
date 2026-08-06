from __future__ import annotations

from core.indicators.momentum import RelativeStrengthIndex
from core.indicators.trend import ExponentialMovingAverage, SimpleMovingAverage
from core.interfaces.types import MarketContext

_FEATURE_NAMES = ["return_1", "sma_distance", "ema_distance", "rsi", "volatility"]


class FeatureExtractor:
    """Builds a numeric feature vector from a MarketContext by replaying the
    same Indicator Engine built-ins (SMA, EMA, RSI) used everywhere else in
    the platform over the bar history -- one indicator implementation reused
    as ML features here, exactly as it's reused in backtest/live/analytics,
    per the architecture's explicit "feature extraction reuses the Indicator
    Engine" requirement.
    """

    def __init__(
        self, *, sma_period: int = 10, ema_period: int = 10, rsi_period: int = 14
    ) -> None:
        if sma_period < 1 or ema_period < 1 or rsi_period < 1:
            raise ValueError("all periods must be >= 1")
        self._sma_period = sma_period
        self._ema_period = ema_period
        self._rsi_period = rsi_period

    def feature_names(self) -> list[str]:
        return list(_FEATURE_NAMES)

    def extract(self, context: MarketContext) -> dict[str, float] | None:
        bars = context.bars
        min_bars = max(self._sma_period, self._ema_period, self._rsi_period + 1) + 1
        if len(bars) < min_bars:
            return None

        sma = SimpleMovingAverage(period=self._sma_period)
        ema = ExponentialMovingAverage(period=self._ema_period)
        rsi = RelativeStrengthIndex(period=self._rsi_period)

        sma_value = ema_value = rsi_value = None
        for bar in bars:
            sma_value = sma.update(bar)
            ema_value = ema.update(bar)
            rsi_value = rsi.update(bar)

        if sma_value is None or ema_value is None or rsi_value is None:
            return None

        current_close = bars[-1].close
        previous_close = bars[-2].close
        return_1 = (current_close - previous_close) / previous_close if previous_close else 0.0

        window = [bar.close for bar in bars[-self._sma_period :]]
        mean_close = sum(window) / len(window)
        variance = sum((close - mean_close) ** 2 for close in window) / len(window)
        volatility = variance**0.5

        return {
            "return_1": return_1,
            "sma_distance": (current_close - sma_value) / sma_value if sma_value else 0.0,
            "ema_distance": (current_close - ema_value) / ema_value if ema_value else 0.0,
            "rsi": rsi_value,
            "volatility": volatility,
        }


__all__ = ["FeatureExtractor"]
