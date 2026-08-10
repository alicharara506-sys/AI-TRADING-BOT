from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Symbol, Timeframe
from machine_learning.labeling.triple_barrier import (
    BarrierHit,
    build_training_labels,
    label_triple_barrier,
)

_SYMBOL = Symbol(name="EURUSD")


def _bar(
    *, index: int, open_: float, high: float, low: float, close: float
) -> Bar:
    return Bar(
        symbol=_SYMBOL,
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1.0,
    )


def _flat_bars(count: int, *, price: float = 100.0, spread: float = 0.05) -> list[Bar]:
    return [
        _bar(index=i, open_=price, high=price + spread, low=price - spread, close=price)
        for i in range(count)
    ]


def test_rejects_invalid_construction_parameters() -> None:
    bars = _flat_bars(40)
    with pytest.raises(ValueError):
        label_triple_barrier(bars, entry_index=20, atr_period=1)
    with pytest.raises(ValueError):
        label_triple_barrier(bars, entry_index=20, upper_multiple=0.0)
    with pytest.raises(ValueError):
        label_triple_barrier(bars, entry_index=20, horizon=0)
    with pytest.raises(ValueError):
        label_triple_barrier(bars, entry_index=999)


def test_none_without_enough_history_for_atr() -> None:
    bars = _flat_bars(40)
    assert label_triple_barrier(bars, entry_index=2, atr_period=14, horizon=5) is None


def test_none_without_a_full_horizon_remaining() -> None:
    bars = _flat_bars(40)
    assert label_triple_barrier(bars, entry_index=35, atr_period=14, horizon=20) is None


def test_upper_barrier_hit_labels_plus_one() -> None:
    bars = _flat_bars(30)
    # Bar 21 (offset 1 from entry_index=20) spikes well above any plausible
    # ATR*1.5 upper barrier given the flat 0.05-wide history before it.
    bars[21] = _bar(index=21, open_=100.0, high=105.0, low=100.0, close=104.0)

    label = label_triple_barrier(bars, entry_index=20, atr_period=14, horizon=5)

    assert label is not None
    assert label.label == 1
    assert label.barrier_hit is BarrierHit.UPPER
    assert label.bars_to_hit == 1


def test_lower_barrier_hit_labels_minus_one() -> None:
    bars = _flat_bars(30)
    bars[21] = _bar(index=21, open_=100.0, high=100.0, low=95.0, close=96.0)

    label = label_triple_barrier(bars, entry_index=20, atr_period=14, horizon=5)

    assert label is not None
    assert label.label == -1
    assert label.barrier_hit is BarrierHit.LOWER
    assert label.bars_to_hit == 1


def test_neither_barrier_hit_within_horizon_labels_zero() -> None:
    bars = _flat_bars(40)

    label = label_triple_barrier(bars, entry_index=20, atr_period=14, horizon=10)

    assert label is not None
    assert label.label == 0
    assert label.barrier_hit is BarrierHit.HORIZONTAL
    assert label.bars_to_hit == 10


def test_both_barriers_touched_in_one_bar_resolves_towards_the_open() -> None:
    bars = _flat_bars(30)
    # Wide-range bar touching both barriers; open sits much closer to the
    # low side, so the tie-break should resolve LOWER.
    bars[21] = _bar(index=21, open_=95.5, high=105.0, low=95.0, close=100.0)

    label = label_triple_barrier(bars, entry_index=20, atr_period=14, horizon=5)

    assert label is not None
    assert label.barrier_hit is BarrierHit.LOWER


def test_build_training_labels_skips_indices_without_enough_data() -> None:
    bars = _flat_bars(40)

    labels = build_training_labels(bars, atr_period=14, horizon=10)

    entry_indices = [entry for entry, _label in labels]
    assert all(14 <= entry < 40 - 10 for entry in entry_indices)
    assert len(labels) > 0


def test_build_training_labels_matches_single_lookups() -> None:
    bars = _flat_bars(40)
    bars[25] = _bar(index=25, open_=100.0, high=110.0, low=100.0, close=108.0)

    labels = dict(build_training_labels(bars, atr_period=14, horizon=5))

    direct = label_triple_barrier(bars, entry_index=24, atr_period=14, horizon=5)
    assert direct is not None
    assert labels[24] == direct
