from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Symbol, Timeframe
from quant.price_action.elliott_wave import find_five_wave_impulse

_SYMBOL = Symbol(name="EURUSD")


def _zigzag(pivots: list[float], *, steps: int = 4) -> list[float]:
    prices: list[float] = []
    for start, end in zip(pivots, pivots[1:], strict=False):
        for step in range(steps):
            prices.append(start + (end - start) * step / steps)
    prices.append(pivots[-1])
    return prices


def _bars(prices: list[float]) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0.0,
        )
        for i, price in enumerate(prices)
    ]


# Pivots P0..P5 for a textbook up-impulse: wave1=0.10, wave2=0.05 (50%
# retracement, doesn't erase wave1), wave3=0.20 (the longest, so never the
# shortest of 1/3/5), wave4=0.10 (stays above P1=1.10, no overlap), wave5=0.08.
_VALID_UP_IMPULSE_PIVOTS = [1.00, 1.10, 1.05, 1.25, 1.15, 1.23]
# Mirror for a down-impulse.
_VALID_DOWN_IMPULSE_PIVOTS = [1.25, 1.15, 1.20, 1.00, 1.10, 1.02]


def _impulse_bars(pivots: list[float]) -> list[Bar]:
    # find_all_swing_points only confirms a bar in range(arm, n - arm) -- P0
    # and P5 both sit at the very edge of the zigzag and are structurally
    # unconfirmable without real bars on their unconfirmed side, so both
    # need genuine lead-in/trail-out bars, not just more of the same ramp.
    first, second = pivots[0], pivots[1]
    leads_up = second > first
    lead = [first + 0.04, first + 0.02] if leads_up else [first - 0.04, first - 0.02]

    last, second_last = pivots[-1], pivots[-2]
    trails_up = last > second_last
    trail = [last - 0.02, last - 0.04] if trails_up else [last + 0.02, last + 0.04]

    return _bars(lead + _zigzag(pivots) + trail)


def test_detects_a_valid_up_impulse() -> None:
    impulse = find_five_wave_impulse(_impulse_bars(_VALID_UP_IMPULSE_PIVOTS), swing_arm=2)

    assert impulse is not None
    assert impulse.direction_up is True
    assert impulse.pivots == (1.00, 1.10, 1.05, 1.25, 1.15, 1.23)
    assert impulse.indices == (2, 6, 10, 14, 18, 22)


def test_detects_a_valid_down_impulse() -> None:
    impulse = find_five_wave_impulse(_impulse_bars(_VALID_DOWN_IMPULSE_PIVOTS), swing_arm=2)

    assert impulse is not None
    assert impulse.direction_up is False


def test_wave2_retracement_and_wave3_extension_ratios() -> None:
    impulse = find_five_wave_impulse(_impulse_bars(_VALID_UP_IMPULSE_PIVOTS), swing_arm=2)

    assert impulse is not None
    assert impulse.wave2_retracement == pytest.approx(0.5)  # 0.05 / 0.10
    assert impulse.wave3_extension == pytest.approx(2.0)  # 0.20 / 0.10


def test_too_few_swing_points_returns_none() -> None:
    bars = _bars(_zigzag([1.00, 1.10, 1.05]))

    assert find_five_wave_impulse(bars, swing_arm=2) is None


def test_rule1_violation_wave2_retraces_past_wave1_start() -> None:
    # P2 = 0.95 < P0 = 1.00 -- wave 2 erased the entirety of wave 1.
    pivots = [1.00, 1.10, 0.95, 1.20, 1.12, 1.30]

    assert find_five_wave_impulse(_impulse_bars(pivots), swing_arm=2) is None


def test_rule2_violation_wave3_is_the_shortest() -> None:
    # wave1=0.30, wave3=0.15 (smallest of the three), wave5=0.20 -- wave 3
    # must never be the shortest of waves 1, 3, 5. P3=1.35 exceeds P1=1.30
    # (required for wave 4 to have room to sit above P1 without overlapping).
    pivots = [1.00, 1.30, 1.20, 1.35, 1.32, 1.52]

    assert find_five_wave_impulse(_impulse_bars(pivots), swing_arm=2) is None


def test_rule3_violation_wave4_overlaps_wave1_territory() -> None:
    # P4 = 1.08 <= P1 = 1.10 -- wave 4 dipped back into wave 1's price range.
    pivots = [1.00, 1.10, 1.05, 1.20, 1.08, 1.15]

    assert find_five_wave_impulse(_impulse_bars(pivots), swing_arm=2) is None
