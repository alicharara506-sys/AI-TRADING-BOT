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

    alternation_holds/is_truncated/wave5_wave1_ratio below are Elliott Wave
    *guidelines*, not rules -- real practice treats them as typicality
    signals, not pass/fail gates, so (unlike the three rules above) a
    candidate failing them is still returned; callers use them as
    confidence-scoring factors instead, the same rule-satisfaction-as-
    confidence approach FibonacciElliottWaveStrategy already applies to
    Fibonacci ratio typicality.
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

    @property
    def wave5_wave1_ratio(self) -> float:
        """Wave 5's length as a multiple of wave 1's. The "equality"
        guideline: when wave 3 is extended, wave 5 often approximately
        equals wave 1 (ratio near 1.0) -- a typicality signal, not a rule.
        """
        return self.wave5 / self.wave1 if self.wave1 > 0 else 0.0

    @property
    def alternation_holds(self) -> bool:
        """The "alternation" guideline: if wave 2 was a deep retracement
        (more than half of wave 1), wave 4 tends to be shallow, and vice
        versa. Approximated here via each wave's own retracement fraction
        sitting on opposite sides of 0.5 -- real Elliott Wave practice also
        judges alternation by corrective *shape* (zigzag vs. flat vs.
        triangle), which needs sub-wave structure this project doesn't
        detect yet, so this is deliberately the checkable depth-only proxy,
        not the full guideline. Rounded to 9 decimal places before
        comparing to 0.5 so a retracement that's mathematically exactly
        50% doesn't flip sides on ordinary floating-point noise.
        """
        return (round(self.wave2_retracement, 9) > 0.5) != (round(self.wave4_retracement, 9) > 0.5)

    @property
    def is_truncated(self) -> bool:
        """A "truncated fifth": wave 5 fails to move beyond wave 3's own
        extreme (a real, if uncommon, pattern Elliott Wave practice
        recognizes rather than a sign of a miscount).
        """
        p3, p5 = self.pivots[3], self.pivots[5]
        return p5 <= p3 if self.direction_up else p5 >= p3


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


@dataclass(frozen=True, slots=True)
class AbcCorrection:
    """A validated 3-wave (A-B-C) corrective structure immediately following
    a completed ImpulseWave: P0 is the impulse's own wave 5 endpoint, then
    A, B, C. Satisfies the objective, checkable part of corrective-wave
    theory: A moves opposite the impulse, B is a partial (not full) retrace
    of A that never breaks back past the impulse's own wave 5 endpoint, and
    C continues in A's direction -- not the subjective judgment of *which*
    corrective pattern (zigzag/flat/triangle) it is.
    """

    pivots: tuple[float, float, float, float]
    indices: tuple[int, int, int, int]

    @property
    def wave_a(self) -> float:
        return abs(self.pivots[1] - self.pivots[0])

    @property
    def wave_b(self) -> float:
        return abs(self.pivots[2] - self.pivots[1])

    @property
    def wave_c(self) -> float:
        return abs(self.pivots[3] - self.pivots[2])

    @property
    def b_retracement(self) -> float:
        """Wave B's retracement as a fraction of wave A's length."""
        return self.wave_b / self.wave_a if self.wave_a > 0 else 0.0

    @property
    def c_extension(self) -> float:
        """Wave C's length as a multiple of wave A's."""
        return self.wave_c / self.wave_a if self.wave_a > 0 else 0.0


def find_abc_correction(
    bars: Sequence[Bar], impulse: ImpulseWave, *, swing_arm: int = 2
) -> AbcCorrection | None:
    """Looks for an A-B-C correction in the three confirmed swing points
    immediately following `impulse`'s own final pivot. None if fewer than 3
    swing points have been confirmed since, if they don't alternate in the
    shape a correction requires, or if B breaks back past the impulse's own
    wave 5 endpoint (which would invalidate the correction, not just make
    it an unusually deep one).
    """
    points = find_all_swing_points(bars, arm=swing_arm)
    impulse_end_index = impulse.indices[-1]
    following = [(index, kind) for index, kind in points if index > impulse_end_index]
    if len(following) < 3:
        return None

    (a_index, a_kind), (b_index, b_kind), (c_index, c_kind) = following[:3]
    expected_a_kind = "low" if impulse.direction_up else "high"
    if a_kind != expected_a_kind or b_kind == a_kind or c_kind != a_kind:
        return None

    p0 = impulse.pivots[-1]
    pa = bars[a_index].low if a_kind == "low" else bars[a_index].high
    pb = bars[b_index].low if b_kind == "low" else bars[b_index].high
    pc = bars[c_index].low if c_kind == "low" else bars[c_index].high

    wave_a = abs(pa - p0)
    if wave_a <= 0:
        return None

    if impulse.direction_up:
        if pb > p0:  # B broke back above the impulse's own wave 5 high
            return None
    else:
        if pb < p0:
            return None

    return AbcCorrection(
        pivots=(p0, pa, pb, pc), indices=(impulse_end_index, a_index, b_index, c_index)
    )


@dataclass(frozen=True, slots=True)
class Diagonal:
    """A validated 5-wave ending diagonal: the same alternating pivot shape
    as ImpulseWave, but with two properties that specifically distinguish a
    diagonal from a regular impulse (which find_five_wave_impulse would
    reject this exact shape from, via its own Rule 3): each successive
    impulse-direction wave is *shorter* than the one before it (a
    contracting wedge), and wave 4 overlaps wave 1's territory -- the
    overlap a regular impulse explicitly forbids.
    """

    direction_up: bool
    pivots: tuple[float, float, float, float, float, float]
    indices: tuple[int, int, int, int, int, int]

    @property
    def wave1(self) -> float:
        return abs(self.pivots[1] - self.pivots[0])

    @property
    def wave3(self) -> float:
        return abs(self.pivots[3] - self.pivots[2])

    @property
    def wave5(self) -> float:
        return abs(self.pivots[5] - self.pivots[4])


def find_ending_diagonal(bars: Sequence[Bar], *, swing_arm: int = 2) -> Diagonal | None:
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
    wave5 = abs(p5 - p4)
    if wave1 <= 0 or wave3 <= 0 or wave5 <= 0:
        return None

    if not (wave3 < wave1 and wave5 < wave3):  # contracting wedge
        return None

    overlaps = p4 <= p1 if direction_up else p4 >= p1
    if not overlaps:  # the defining diagonal feature -- absent, it's just an impulse
        return None

    return Diagonal(
        direction_up=direction_up,
        pivots=(p0, p1, p2, p3, p4, p5),
        indices=(i0, i1, i2, i3, i4, i5),
    )


__all__ = [
    "AbcCorrection",
    "Diagonal",
    "ImpulseWave",
    "find_abc_correction",
    "find_ending_diagonal",
    "find_five_wave_impulse",
]
