from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.technical_analysis.volume_profile import VolumeProfileModule, compute_volume_profile

_SYMBOL = Symbol(name="EURUSD")


def _bars(ohlcv: list[tuple[float, float, float, float, float]]) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=v,
        )
        for i, (o, h, low, c, v) in enumerate(ohlcv)
    ]


# Price range 100-110 spans exactly 10 bins of width 1 when bins=10. Two
# thin bars establish the full range; two heavy bars concentrate volume in
# bins 4 ([104, 105)) and 5 ([105, 106)), with bin 5 the heaviest -- the
# known point of control.
_PROFILE_BARS = _bars(
    [
        (100.0, 101.0, 100.0, 100.5, 1.0),
        (109.0, 110.0, 109.0, 109.5, 1.0),
        (104.0, 106.0, 104.0, 105.0, 50.0),
        (105.0, 106.0, 105.0, 105.5, 10.0),
    ]
)


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        compute_volume_profile(_PROFILE_BARS, bins=0)
    with pytest.raises(ValueError):
        compute_volume_profile(_PROFILE_BARS, value_area_fraction=0.0)
    with pytest.raises(ValueError):
        compute_volume_profile(_PROFILE_BARS, value_area_fraction=1.5)


def test_point_of_control_lands_at_the_heaviest_bin() -> None:
    profile = compute_volume_profile(_PROFILE_BARS, bins=10)

    assert profile is not None
    assert profile.point_of_control == pytest.approx(105.5)


def test_value_area_covers_the_target_fraction_around_the_poc() -> None:
    profile = compute_volume_profile(_PROFILE_BARS, bins=10, value_area_fraction=0.7)

    assert profile is not None
    assert profile.value_area_low == pytest.approx(104.0)
    assert profile.value_area_high == pytest.approx(106.0)
    assert profile.total_volume == pytest.approx(62.0)


def test_too_few_bars_returns_none() -> None:
    assert compute_volume_profile(_bars([(1.0, 1.0, 1.0, 1.0, 1.0)]), bins=10) is None


def test_degenerate_flat_range_returns_none() -> None:
    flat = _bars([(1.0, 1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 1.0, 1.0)])

    assert compute_volume_profile(flat, bins=10) is None


def test_zero_volume_bars_return_none() -> None:
    zero_volume = _bars([(1.0, 1.1, 0.9, 1.0, 0.0), (1.0, 1.2, 0.8, 1.1, 0.0)])

    assert compute_volume_profile(zero_volume, bins=10) is None


def test_module_emits_short_evidence_above_the_value_area() -> None:
    module = VolumeProfileModule(bins=10)
    bars = [*_PROFILE_BARS, *_bars([(108.0, 108.0, 108.0, 108.0, 1.0)])]

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].rationale["value_area_high"] == pytest.approx(106.0)


def test_module_emits_long_evidence_below_the_value_area() -> None:
    module = VolumeProfileModule(bins=10)
    bars = [*_PROFILE_BARS, *_bars([(101.5, 101.5, 101.5, 101.5, 1.0)])]

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_module_emits_no_evidence_inside_the_value_area() -> None:
    module = VolumeProfileModule(bins=10)
    bars = [*_PROFILE_BARS, *_bars([(105.0, 105.0, 105.0, 105.0, 1.0)])]

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars))) == []


def test_module_returns_no_evidence_with_too_few_bars() -> None:
    module = VolumeProfileModule(bins=10)
    single_bar = tuple(_bars([(1.0, 1.0, 1.0, 1.0, 1.0)]))

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=single_bar)) == []
