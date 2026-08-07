from __future__ import annotations

from collections.abc import Sequence

from core.indicators.trend import ExponentialMovingAverage
from core.interfaces.types import Bar, Direction, Evidence, MarketContext
from quant.technical_analysis.volatility import compute_atr


def compute_bollinger_bands(
    bars: Sequence[Bar], *, period: int = 20, num_std: float = 2.0
) -> tuple[float, float, float] | None:
    """(mean, upper, lower): a simple moving average of closes over `period`
    bars, with bands `num_std` population standard deviations above/below --
    the standard Bollinger Band definition. None until there's enough
    history.
    """
    if period < 2:
        raise ValueError("period must be >= 2")
    if num_std <= 0:
        raise ValueError("num_std must be > 0")
    if len(bars) < period:
        return None

    window = [bar.close for bar in bars[-period:]]
    mean = sum(window) / period
    variance = sum((close - mean) ** 2 for close in window) / period
    std = variance**0.5
    return mean, mean + num_std * std, mean - num_std * std


class BollingerBandModule:
    """Mean-reversion at the Bollinger Bands: a close beyond either band is
    evidence of a snap-back toward the mean (the classic range-bound read of
    Bollinger Bands, as distinct from Keltner/Donchian's breakout read
    below), with confidence scaled by how far beyond the band price closed,
    relative to the band's own width.
    """

    name = "bollinger_band_reversion"

    def __init__(self, *, period: int = 20, num_std: float = 2.0) -> None:
        self._period = period
        self._num_std = num_std

    def analyze(self, context: MarketContext) -> list[Evidence]:
        result = compute_bollinger_bands(context.bars, period=self._period, num_std=self._num_std)
        if result is None:
            return []

        mean, upper, lower = result
        band_width = upper - lower
        if band_width <= 0:
            return []

        current = context.bars[-1].close
        if current > upper:
            direction, distance = Direction.SHORT, current - upper
        elif current < lower:
            direction, distance = Direction.LONG, lower - current
        else:
            return []

        confidence = min(distance / band_width, 1.0)
        if confidence <= 0.0:
            return []

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={"mean": mean, "upper": upper, "lower": lower, "current": current},
            )
        ]


def compute_keltner_channels(
    bars: Sequence[Bar], *, period: int = 20, atr_period: int = 10, multiplier: float = 2.0
) -> tuple[float, float, float] | None:
    """(middle, upper, lower): an EMA of closes over `period` bars, with
    bands `multiplier` ATRs above/below -- the standard Keltner Channel
    definition. Reuses the same ExponentialMovingAverage class the
    Indicator Engine already exposes and compute_atr from this package
    rather than reimplementing either.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if multiplier <= 0:
        raise ValueError("multiplier must be > 0")
    if len(bars) < period:
        return None

    atr = compute_atr(bars, period=atr_period)
    if atr is None:
        return None

    ema = ExponentialMovingAverage(period)
    middle: float | None = None
    for bar in bars[-period:]:
        middle = ema.update(bar)
    if middle is None:
        return None

    return middle, middle + multiplier * atr, middle - multiplier * atr


class KeltnerChannelModule:
    """Keltner Channel breakout: a close beyond either band is evidence of
    trend continuation in that direction (the standard breakout read of
    Keltner Channels), with confidence scaled by how far beyond the band
    price closed, relative to the channel's own width.
    """

    name = "keltner_channel_breakout"

    def __init__(
        self, *, period: int = 20, atr_period: int = 10, multiplier: float = 2.0
    ) -> None:
        self._period = period
        self._atr_period = atr_period
        self._multiplier = multiplier

    def analyze(self, context: MarketContext) -> list[Evidence]:
        result = compute_keltner_channels(
            context.bars,
            period=self._period,
            atr_period=self._atr_period,
            multiplier=self._multiplier,
        )
        if result is None:
            return []

        _middle, upper, lower = result
        channel_width = upper - lower
        if channel_width <= 0:
            return []

        current = context.bars[-1].close
        if current > upper:
            direction, distance = Direction.LONG, current - upper
        elif current < lower:
            direction, distance = Direction.SHORT, lower - current
        else:
            return []

        confidence = min(distance / channel_width, 1.0)
        if confidence <= 0.0:
            return []

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={"upper": upper, "lower": lower, "current": current},
            )
        ]


def compute_donchian_channels(
    bars: Sequence[Bar], *, period: int = 20
) -> tuple[float, float] | None:
    """(upper, lower): the highest high and lowest low over the last `period`
    bars -- the classic Turtle Trading channel. None until there's enough
    history.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(bars) < period:
        return None

    window = bars[-period:]
    return max(bar.high for bar in window), min(bar.low for bar in window)


class DonchianBreakoutModule:
    """Donchian Channel breakout: a close beyond the highest high/lowest low
    of the *preceding* `period` bars (the current bar itself is excluded
    from the channel it's tested against, or every breakout would trivially
    "break" its own extreme) is evidence of continuation, confidence scaled
    by breakout size relative to the channel's own width.
    """

    name = "donchian_breakout"

    def __init__(self, *, period: int = 20) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self._period = period

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        if len(bars) < self._period + 1:
            return []

        channel = compute_donchian_channels(bars[:-1], period=self._period)
        if channel is None:
            return []

        upper, lower = channel
        channel_width = upper - lower
        if channel_width <= 0:
            return []

        current = bars[-1].close
        if current > upper:
            direction, distance = Direction.LONG, current - upper
        elif current < lower:
            direction, distance = Direction.SHORT, lower - current
        else:
            return []

        confidence = min(distance / channel_width, 1.0)
        if confidence <= 0.0:
            return []

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={"upper": upper, "lower": lower, "current": current},
            )
        ]


__all__ = [
    "BollingerBandModule",
    "DonchianBreakoutModule",
    "KeltnerChannelModule",
    "compute_bollinger_bands",
    "compute_donchian_channels",
    "compute_keltner_channels",
]
