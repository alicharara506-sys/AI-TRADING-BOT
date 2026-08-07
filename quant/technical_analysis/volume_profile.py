from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.interfaces.types import Bar, Direction, Evidence, MarketContext

_DEFAULT_BINS = 24
_DEFAULT_VALUE_AREA_FRACTION = 0.7


@dataclass(frozen=True, slots=True)
class VolumeProfileLevel:
    """One price bin's traded volume. `price` is the bin's midpoint."""

    price: float
    volume: float


@dataclass(frozen=True, slots=True)
class VolumeProfile:
    """A price-by-volume histogram over a window of bars: which price levels
    traded the most volume (point of control), and the contiguous band of
    levels holding `value_area_fraction` of total volume around it (value
    area) -- the standard volume-profile definitions used for support/
    resistance and mean-reversion analysis.
    """

    levels: tuple[VolumeProfileLevel, ...]
    point_of_control: float
    value_area_low: float
    value_area_high: float
    total_volume: float


def compute_volume_profile(
    bars: Sequence[Bar],
    *,
    bins: int = _DEFAULT_BINS,
    value_area_fraction: float = _DEFAULT_VALUE_AREA_FRACTION,
) -> VolumeProfile | None:
    """Builds a volume profile over `bars`. Each bar's volume is distributed
    across every price bin its [low, high] range overlaps, proportional to
    the overlap -- not dumped into a single bin at its close -- since a bar
    genuinely traded across its whole range, not just at one price.

    Returns None when there aren't at least 2 bars, every bar has zero
    volume (MT5 forex/CFD symbols commonly report tick volume, not real
    traded volume, but zero is zero either way), or the bars' combined
    range is degenerate (high == low for every bar), since no meaningful
    histogram can be built in either case.
    """
    if bins < 1:
        raise ValueError("bins must be >= 1")
    if not 0.0 < value_area_fraction <= 1.0:
        raise ValueError("value_area_fraction must be in (0.0, 1.0]")
    if len(bars) < 2:
        return None

    price_min = min(bar.low for bar in bars)
    price_max = max(bar.high for bar in bars)
    if price_max <= price_min:
        return None

    bin_width = (price_max - price_min) / bins
    bin_volumes = [0.0] * bins

    for bar in bars:
        if bar.volume <= 0:
            continue
        bar_low, bar_high = bar.low, bar.high
        if bar_high <= bar_low:
            index = min(int((bar_low - price_min) / bin_width), bins - 1)
            bin_volumes[index] += bar.volume
            continue

        first_bin = min(int((bar_low - price_min) / bin_width), bins - 1)
        last_bin = min(int((bar_high - price_min) / bin_width), bins - 1)
        bar_range = bar_high - bar_low
        for index in range(first_bin, last_bin + 1):
            bin_lo = price_min + index * bin_width
            bin_hi = bin_lo + bin_width
            overlap = min(bar_high, bin_hi) - max(bar_low, bin_lo)
            if overlap <= 0:
                continue
            bin_volumes[index] += bar.volume * (overlap / bar_range)

    total_volume = sum(bin_volumes)
    if total_volume <= 0:
        return None

    levels = tuple(
        VolumeProfileLevel(price=price_min + (index + 0.5) * bin_width, volume=volume)
        for index, volume in enumerate(bin_volumes)
    )

    poc_index = max(range(bins), key=lambda index: bin_volumes[index])
    value_area_indices = _expand_value_area(
        bin_volumes, poc_index, total_volume, value_area_fraction
    )
    value_area_low = price_min + min(value_area_indices) * bin_width
    value_area_high = price_min + (max(value_area_indices) + 1) * bin_width

    return VolumeProfile(
        levels=levels,
        point_of_control=levels[poc_index].price,
        value_area_low=value_area_low,
        value_area_high=value_area_high,
        total_volume=total_volume,
    )


def _expand_value_area(
    bin_volumes: list[float], poc_index: int, total_volume: float, value_area_fraction: float
) -> set[int]:
    included = {poc_index}
    accumulated = bin_volumes[poc_index]
    target = total_volume * value_area_fraction
    low, high = poc_index - 1, poc_index + 1

    while accumulated < target and (low >= 0 or high < len(bin_volumes)):
        low_volume = bin_volumes[low] if low >= 0 else -1.0
        high_volume = bin_volumes[high] if high < len(bin_volumes) else -1.0
        if high_volume >= low_volume:
            included.add(high)
            accumulated += high_volume
            high += 1
        else:
            included.add(low)
            accumulated += low_volume
            low -= 1

    return included


class VolumeProfileModule:
    """Wraps compute_volume_profile as an AnalysisModule: when the latest
    price sits outside the value area, that's evidence of reversion back
    toward it (the standard volume-profile trading read -- price tends to
    revisit the range that absorbed most volume), with confidence scaled by
    how far outside the value area price has moved relative to its width.
    Price inside the value area is not itself directional evidence, so no
    Evidence is emitted in that case -- same "return [] rather than force a
    call" discipline as FibonacciConfluenceModule.
    """

    name = "volume_profile"

    def __init__(
        self,
        *,
        bins: int = _DEFAULT_BINS,
        value_area_fraction: float = _DEFAULT_VALUE_AREA_FRACTION,
        lookback: int = 200,
    ) -> None:
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        self._bins = bins
        self._value_area_fraction = value_area_fraction
        self._lookback = lookback

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = list(context.bars)[-self._lookback :]
        profile = compute_volume_profile(
            bars, bins=self._bins, value_area_fraction=self._value_area_fraction
        )
        if profile is None:
            return []

        value_area_width = profile.value_area_high - profile.value_area_low
        if value_area_width <= 0:
            return []

        current = bars[-1].close
        if current > profile.value_area_high:
            distance = current - profile.value_area_high
            direction = Direction.SHORT
        elif current < profile.value_area_low:
            distance = profile.value_area_low - current
            direction = Direction.LONG
        else:
            return []

        confidence = min(distance / value_area_width, 1.0)
        if confidence <= 0.0:
            return []

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={
                    "point_of_control": profile.point_of_control,
                    "value_area_low": profile.value_area_low,
                    "value_area_high": profile.value_area_high,
                },
                supporting_data={"current": current, "total_volume": profile.total_volume},
            )
        ]


__all__ = ["VolumeProfile", "VolumeProfileLevel", "VolumeProfileModule", "compute_volume_profile"]
