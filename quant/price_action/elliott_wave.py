from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.interfaces.types import Bar
from quant.price_action.swings import find_all_swing_points

_UP_PATTERN = ("low", "high", "low", "high", "low", "high")
_DOWN_PATTERN = ("high", "low", "high", "low", "high", "low")


@dataclass(frozen=True, slots=True)
class ImpulseWave:
    """A validated 5-wave Elliott impulse: six pivot points (P0..P5) over the
    shared swing-point primitive (quant/price_action/swings.py), satisfying
    the three rules of Elliott Wave theory that are objective and mechanical
    -- not the subjective "does this count look right" judgment real Elliott
    Wave practice is notorious for disagreeing on:

        1. wave 2 never retraces more than 100% of wave 1
        2. wave 3 is never the shortest of waves 1, 3, 5
        3. wave 4 never overlaps wave 1's price territory (non-diagonal case)

    find_five_wave_impulse() only ever returns a candidate that already
    satisfies all three -- there is no "invalid but returned anyway" state.
    """

    direction_up: bool
    pivots: tuple[float, float, float, float, float, float]
    indices: tuple[int, int, int, int, int, int]

    @property
    def wave1(self) -> float:
        return abs(self.pivots[1] - self.pivots[0])

    @property
    def wave2(self) -> float:
        return abs(self.pivots[2] - self.pivots[1])

    @property
    def wave3(self) -> float:
        return abs(self.pivots[3] - self.pivots[2])

    @property
    def wave4(self) -> float:
        return abs(self.pivots[4] - self.pivots[3])

    @property
    def wave5(self) -> float:
        return abs(self.pivots[5] - self.pivots[4])

    @property
    def wave2_retracement(self) -> float:
        """Wave 2's retracement as a fraction of wave 1's length."""
        return self.wave2 / self.wave1 if self.wave1 > 0 else 0.0

    @property
    def wave4_retracement(self) -> float:
        """Wave 4's retracement as a fraction of wave 3's length."""
        return self.wave4 / self.wave3 if self.wave3 > 0 else 0.0

    @property
    def wave3_extension(self) -> float:
        """Wave 3's length as a multiple of wave 1's -- typically >= 1.0,
        often close to the 1.618 Fibonacci extension in a textbook impulse."""
        return self.wave3 / self.wave1 if self.wave1 > 0 else 0.0


def find_five_wave_impulse(bars: Sequence[Bar], *, swing_arm: int = 2) -> ImpulseWave | None:
    """Looks for a valid 5-wave impulse ending at the most recent confirmed
    swing point, using the last 6 confirmed swing points in `bars`. Returns
    None if there aren't 6 yet, if they don't alternate high/low/high/...
    (i.e. don't form a clean impulse shape at all), or if any of the three
    objective Elliott Wave rules is violated.
    """
    points = find_all_swing_points(bars, arm=swing_arm)
    if len(points) < 6:
        return None

    last_six = points[-6:]
    kinds = tuple(kind for _, kind in last_six)
    if kinds == _UP_PATTERN:
        direction_up = True
    elif kinds == _DOWN_PATTERN:
        direction_up = False
    else:
        return None

    i0, i1, i2, i3, i4, i5 = (index for index, _ in last_six)
    p0, p1, p2, p3, p4, p5 = (
        bars[index].high if kind == "high" else bars[index].low for index, kind in last_six
    )

    wave1 = abs(p1 - p0)
    wave3 = abs(p3 - p2)
    if wave1 <= 0 or wave3 <= 0:
        return None

    if direction_up:
        if p2 <= p0:  # Rule 1: wave 2 retraced all of wave 1
            return None
        if p4 <= p1:  # Rule 3: wave 4 overlapped wave 1's territory
            return None
    else:
        if p2 >= p0:
            return None
        if p4 >= p1:
            return None

    wave5 = abs(p5 - p4)
    if wave3 < wave1 and wave3 < wave5:  # Rule 2: wave 3 was the shortest
        return None

    return ImpulseWave(
        direction_up=direction_up,
        pivots=(p0, p1, p2, p3, p4, p5),
        indices=(i0, i1, i2, i3, i4, i5),
    )


__all__ = ["ImpulseWave", "find_five_wave_impulse"]
