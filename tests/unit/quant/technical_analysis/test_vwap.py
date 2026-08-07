from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.technical_analysis.vwap import (
    AnchoredVwapModule,
    compute_anchored_vwap,
    compute_vwap,
)

_SYMBOL = Symbol(name="EURUSD")

# Reused from the shared swing-detection tests: swing low at index 3 (1.00),
# swing high at index 10 (1.20), confirmed with arm=2.
_SWING_PRICES = [1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18, 1.16]


def _bars(hlcv: list[tuple[float, float, float, float]]) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=c,
            high=h,
            low=low,
            close=c,
            volume=v,
        )
        for i, (h, low, c, v) in enumerate(hlcv)
    ]


def _price_bars(prices: list[float], *, volume: float = 10.0) -> list[Bar]:
    return _bars([(p, p, p, volume) for p in prices])


# -- compute_vwap / compute_anchored_vwap ---------------------------------


def test_compute_vwap_matches_hand_computed_values() -> None:
    bars = _bars([(10.0, 8.0, 9.0, 100.0), (12.0, 10.0, 11.0, 200.0)])

    vwap = compute_vwap(bars, period=2)

    # typical prices: 9.0 and 11.0; weighted = 9*100 + 11*200 = 3100; /300
    assert vwap == pytest.approx(3100.0 / 300.0)


def test_compute_vwap_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        compute_vwap(_bars([(1.0, 1.0, 1.0, 1.0)]), period=0)


def test_compute_vwap_returns_none_with_insufficient_bars() -> None:
    assert compute_vwap(_bars([(1.0, 1.0, 1.0, 1.0)]), period=5) is None


def test_compute_vwap_returns_none_with_zero_total_volume() -> None:
    bars = _bars([(1.0, 1.0, 1.0, 0.0), (1.0, 1.0, 1.0, 0.0)])

    assert compute_vwap(bars, period=2) is None


def test_compute_anchored_vwap_matches_a_trailing_window_at_the_same_anchor() -> None:
    bars = _bars([(10.0, 8.0, 9.0, 100.0), (12.0, 10.0, 11.0, 200.0), (14.0, 12.0, 13.0, 50.0)])

    anchored = compute_anchored_vwap(bars, anchor_index=1)
    trailing = compute_vwap(bars, period=2)

    assert anchored == pytest.approx(trailing)


def test_compute_anchored_vwap_rejects_an_out_of_range_index() -> None:
    bars = _bars([(1.0, 1.0, 1.0, 1.0)])
    with pytest.raises(ValueError):
        compute_anchored_vwap(bars, anchor_index=1)
    with pytest.raises(ValueError):
        compute_anchored_vwap(bars, anchor_index=-1)


# -- AnchoredVwapModule ------------------------------------------------------


def test_module_emits_short_evidence_when_price_pulls_back_below_the_anchor() -> None:
    module = AnchoredVwapModule(swing_arm=2, atr_period=5)
    bars = _price_bars(_SWING_PRICES)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].rationale["anchor_index"] == 10


def test_module_emits_long_evidence_when_price_bounces_above_the_anchor() -> None:
    module = AnchoredVwapModule(swing_arm=2, atr_period=5)
    mirrored_prices = [2.0 - p for p in _SWING_PRICES]
    bars = _price_bars(mirrored_prices)

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_module_emits_no_evidence_with_too_few_bars() -> None:
    module = AnchoredVwapModule(swing_arm=2, atr_period=5)

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(_price_bars([1.0, 1.1])))) == []


def test_module_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        AnchoredVwapModule(swing_arm=0)
    with pytest.raises(ValueError):
        AnchoredVwapModule(atr_period=1)
