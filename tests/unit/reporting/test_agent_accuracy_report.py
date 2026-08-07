from __future__ import annotations

import pytest

from analytics.hit_rate_store import HistoricalHitRateStore
from reporting.agent_accuracy_report import AgentAccuracyReport


def test_from_store_lists_every_tracked_module_symbol_pair_sorted() -> None:
    store = HistoricalHitRateStore(min_samples=2)
    store.record_outcome("market_structure", "GBPUSD", won=True)
    store.record_outcome("market_structure", "GBPUSD", won=True)
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)
    store.record_outcome("engulfing_pattern", "EURUSD", won=False)

    report = AgentAccuracyReport.from_store(store)

    assert len(report.modules) == 2
    assert report.modules[0].module_name == "engulfing_pattern"
    assert report.modules[0].symbol == "EURUSD"
    assert report.modules[0].hit_rate == pytest.approx(0.5)
    assert report.modules[0].sample_count == 2
    assert report.modules[1].module_name == "market_structure"
    assert report.modules[1].hit_rate == pytest.approx(1.0)


def test_from_store_reports_none_hit_rate_below_the_minimum_sample_count() -> None:
    store = HistoricalHitRateStore(min_samples=5)
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)

    report = AgentAccuracyReport.from_store(store)

    assert report.modules[0].hit_rate is None
    assert report.modules[0].sample_count == 1


def test_from_store_is_empty_for_a_fresh_store() -> None:
    report = AgentAccuracyReport.from_store(HistoricalHitRateStore())

    assert report.modules == ()


def test_render_includes_every_module_and_handles_missing_hit_rate() -> None:
    store = HistoricalHitRateStore(min_samples=5)
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)

    rendered = AgentAccuracyReport.from_store(store).render()

    assert "engulfing_pattern" in rendered
    assert "EURUSD" in rendered
    assert "not enough data" in rendered


def test_render_shows_a_percentage_once_the_minimum_is_reached() -> None:
    store = HistoricalHitRateStore(min_samples=2)
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)

    rendered = AgentAccuracyReport.from_store(store).render()

    assert "100.0%" in rendered


def test_render_with_no_outcomes_says_so() -> None:
    rendered = AgentAccuracyReport.from_store(HistoricalHitRateStore()).render()

    assert "no outcomes recorded yet" in rendered
