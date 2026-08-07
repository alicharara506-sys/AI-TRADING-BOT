from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.price_action.smart_money_concepts import (
    FairValueGapModule,
    LiquiditySweepModule,
    find_equal_highs_lows,
    find_fair_value_gaps,
    find_liquidity_sweeps,
    find_order_blocks,
)

_SYMBOL = Symbol(name="EURUSD")


def _bar(o: float, h: float, low: float, c: float, i: int) -> Bar:
    return Bar(
        symbol=_SYMBOL,
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=1.0,
    )


def _flat_bars(prices: list[float]) -> list[Bar]:
    return [_bar(p, p, p, p, i) for i, p in enumerate(prices)]


# -- Fair value gaps -----------------------------------------------------------


def test_find_fair_value_gaps_detects_a_bullish_gap() -> None:
    bars = [
        _bar(1.10, 1.11, 1.09, 1.10, 0),
        _bar(1.10, 1.20, 1.10, 1.19, 1),  # displacement candle
        _bar(1.19, 1.22, 1.15, 1.20, 2),  # low (1.15) still above candle 0's high (1.11)
    ]

    gaps = find_fair_value_gaps(bars)

    assert len(gaps) == 1
    assert gaps[0].direction_up is True
    assert gaps[0].index == 1
    assert gaps[0].gap_low == pytest.approx(1.11)
    assert gaps[0].gap_high == pytest.approx(1.15)


def test_find_fair_value_gaps_detects_a_bearish_gap() -> None:
    bars = [
        _bar(1.20, 1.21, 1.19, 1.20, 0),
        _bar(1.20, 1.10, 1.05, 1.06, 1),
        _bar(1.06, 1.09, 1.02, 1.03, 2),  # high (1.09) still below candle 0's low (1.19)
    ]

    gaps = find_fair_value_gaps(bars)

    assert len(gaps) == 1
    assert gaps[0].direction_up is False
    assert gaps[0].gap_low == pytest.approx(1.09)
    assert gaps[0].gap_high == pytest.approx(1.19)


def test_find_fair_value_gaps_finds_none_in_overlapping_candles() -> None:
    bars = [
        _bar(1.10, 1.12, 1.08, 1.11, 0),
        _bar(1.11, 1.13, 1.09, 1.12, 1),
        _bar(1.12, 1.14, 1.10, 1.13, 2),
    ]

    assert find_fair_value_gaps(bars) == []


def test_fair_value_gap_module_emits_long_evidence_when_price_sits_inside_an_up_gap() -> None:
    module = FairValueGapModule(lookback=10)
    bars = [
        _bar(1.10, 1.11, 1.09, 1.10, 0),
        _bar(1.10, 1.20, 1.10, 1.19, 1),
        _bar(1.19, 1.22, 1.15, 1.20, 2),
        _bar(1.20, 1.20, 1.13, 1.13, 3),  # pulls back into the [1.11, 1.15] gap
    ]

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG


def test_fair_value_gap_module_emits_no_evidence_outside_any_gap() -> None:
    module = FairValueGapModule(lookback=10)
    bars = [
        _bar(1.10, 1.11, 1.09, 1.10, 0),
        _bar(1.10, 1.20, 1.10, 1.19, 1),
        _bar(1.19, 1.22, 1.15, 1.20, 2),
        _bar(1.20, 1.25, 1.20, 1.24, 3),  # stays well above the gap
    ]

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars))) == []


# -- Equal highs / lows ------------------------------------------------------


def test_find_equal_highs_lows_detects_a_near_equal_high_pair() -> None:
    prices = [
        1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18,
        1.16, 1.14, 1.12, 1.10, 1.13, 1.16, 1.1999, 1.17, 1.15,
    ]
    bars = _flat_bars(prices)

    levels = find_equal_highs_lows(bars, swing_arm=2, tolerance=0.001)

    assert len(levels) == 1
    assert levels[0].is_high is True
    assert levels[0].index_a == 10
    assert levels[0].index_b == 18
    assert levels[0].price == pytest.approx(1.19995)


def test_find_equal_highs_lows_rejects_a_pair_outside_tolerance() -> None:
    prices = [
        1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18,
        1.16, 1.14, 1.12, 1.10, 1.13, 1.16, 1.25, 1.17, 1.15,
    ]
    bars = _flat_bars(prices)

    assert find_equal_highs_lows(bars, swing_arm=2, tolerance=0.001) == []


def test_find_equal_highs_lows_rejects_invalid_parameters() -> None:
    bars = _flat_bars([1.0] * 10)
    with pytest.raises(ValueError):
        find_equal_highs_lows(bars, swing_arm=0)
    with pytest.raises(ValueError):
        find_equal_highs_lows(bars, tolerance=0.0)


# -- Order blocks ------------------------------------------------------------


def test_find_order_blocks_finds_the_last_opposite_candle_before_a_displacement() -> None:
    bars = [_bar(10.0, 10.05, 9.95, 10.0, i) for i in range(20)]
    bars.append(_bar(10.0, 10.02, 9.9, 9.92, 20))  # bearish candle
    bars.append(_bar(9.92, 11.5, 9.9, 11.4, 21))  # bullish displacement

    order_blocks = find_order_blocks(bars, atr_period=5, displacement_multiple=1.5)

    assert len(order_blocks) == 1
    assert order_blocks[0].bullish is True
    assert order_blocks[0].index == 20
    assert order_blocks[0].high == pytest.approx(10.02)
    assert order_blocks[0].low == pytest.approx(9.9)


def test_find_order_blocks_finds_none_without_a_displacement_move() -> None:
    bars = [_bar(10.0, 10.05, 9.95, 10.0 + 0.001 * (i % 2), i) for i in range(30)]

    assert find_order_blocks(bars, atr_period=5, displacement_multiple=1.5) == []


def test_find_order_blocks_rejects_invalid_parameters() -> None:
    bars = _flat_bars([1.0] * 30)
    with pytest.raises(ValueError):
        find_order_blocks(bars, atr_period=1)
    with pytest.raises(ValueError):
        find_order_blocks(bars, displacement_multiple=1.0)


# -- Liquidity sweeps ----------------------------------------------------------


_SWEEP_SETUP_PRICES = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18,
    1.16, 1.14, 1.12, 1.10,
]


def test_find_liquidity_sweeps_detects_a_swept_high() -> None:
    bars = _flat_bars(_SWEEP_SETUP_PRICES)
    sweep_bar = _bar(1.15, 1.25, 1.14, 1.19, len(bars))
    bars_with_sweep = [*bars, sweep_bar]

    sweeps = find_liquidity_sweeps(bars_with_sweep, swing_arm=2)

    assert len(sweeps) == 1
    assert sweeps[0].swept_high is True
    assert sweeps[0].index == 16
    assert sweeps[0].swept_level == pytest.approx(1.20)


def test_find_liquidity_sweeps_finds_none_when_price_stays_inside_the_range() -> None:
    bars = _flat_bars(_SWEEP_SETUP_PRICES)
    calm_bar = _bar(1.15, 1.16, 1.14, 1.15, len(bars))

    assert find_liquidity_sweeps([*bars, calm_bar], swing_arm=2) == []


def test_liquidity_sweep_module_emits_short_evidence_on_the_current_bar() -> None:
    module = LiquiditySweepModule(swing_arm=2)
    bars = _flat_bars(_SWEEP_SETUP_PRICES)
    sweep_bar = _bar(1.15, 1.25, 1.14, 1.19, len(bars))
    bars_with_sweep = tuple([*bars, sweep_bar])

    evidence = module.analyze(MarketContext(symbol=_SYMBOL, bars=bars_with_sweep))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].rationale["swept_level"] == pytest.approx(1.20)


def test_liquidity_sweep_module_emits_no_evidence_when_the_sweep_is_not_on_the_last_bar() -> None:
    module = LiquiditySweepModule(swing_arm=2)
    bars = _flat_bars(_SWEEP_SETUP_PRICES)
    sweep_bar = _bar(1.15, 1.25, 1.14, 1.19, len(bars))
    trailing_bar = _bar(1.19, 1.19, 1.18, 1.185, len(bars) + 1)
    bars_with_sweep = tuple([*bars, sweep_bar, trailing_bar])

    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=bars_with_sweep)) == []


def test_liquidity_sweep_module_emits_no_evidence_with_too_few_bars() -> None:
    module = LiquiditySweepModule(swing_arm=2)

    bars = tuple(_flat_bars([1.0, 1.1]))
    assert module.analyze(MarketContext(symbol=_SYMBOL, bars=bars)) == []
