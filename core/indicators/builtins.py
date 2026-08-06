from __future__ import annotations

from core.indicators.momentum import RelativeStrengthIndex
from core.indicators.registry import IndicatorRegistry
from core.indicators.trend import ExponentialMovingAverage, SimpleMovingAverage


def register_builtin_indicators(registry: IndicatorRegistry) -> None:
    registry.register("sma_20", lambda: SimpleMovingAverage(period=20))
    registry.register("sma_50", lambda: SimpleMovingAverage(period=50))
    registry.register("ema_12", lambda: ExponentialMovingAverage(period=12))
    registry.register("ema_26", lambda: ExponentialMovingAverage(period=26))
    registry.register("rsi_14", lambda: RelativeStrengthIndex(period=14))


__all__ = ["register_builtin_indicators"]
