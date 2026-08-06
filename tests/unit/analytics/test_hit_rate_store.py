from __future__ import annotations

import pytest

from analytics.hit_rate_store import HistoricalHitRateStore


def test_rejects_invalid_min_samples() -> None:
    with pytest.raises(ValueError):
        HistoricalHitRateStore(min_samples=0)


def test_hit_rate_is_none_before_minimum_samples() -> None:
    store = HistoricalHitRateStore(min_samples=5)
    for _ in range(4):
        store.record_outcome("engulfing_pattern", "EURUSD", won=True)

    assert store.hit_rate("engulfing_pattern", "EURUSD") is None
    assert store.sample_count("engulfing_pattern", "EURUSD") == 4


def test_hit_rate_computed_once_minimum_reached() -> None:
    store = HistoricalHitRateStore(min_samples=5)
    outcomes = [True, True, False, True, False]
    for won in outcomes:
        store.record_outcome("engulfing_pattern", "EURUSD", won=won)

    assert store.hit_rate("engulfing_pattern", "EURUSD") == pytest.approx(3 / 5)
    assert store.sample_count("engulfing_pattern", "EURUSD") == 5


def test_outcomes_are_isolated_per_module_and_symbol() -> None:
    store = HistoricalHitRateStore(min_samples=2)
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)
    store.record_outcome("engulfing_pattern", "GBPUSD", won=False)
    store.record_outcome("engulfing_pattern", "GBPUSD", won=False)
    store.record_outcome("market_structure", "EURUSD", won=False)
    store.record_outcome("market_structure", "EURUSD", won=False)

    assert store.hit_rate("engulfing_pattern", "EURUSD") == pytest.approx(1.0)
    assert store.hit_rate("engulfing_pattern", "GBPUSD") == pytest.approx(0.0)
    assert store.hit_rate("market_structure", "EURUSD") == pytest.approx(0.0)


def test_unknown_module_or_symbol_has_zero_samples_and_no_hit_rate() -> None:
    store = HistoricalHitRateStore(min_samples=5)

    assert store.sample_count("nonexistent", "EURUSD") == 0
    assert store.hit_rate("nonexistent", "EURUSD") is None
