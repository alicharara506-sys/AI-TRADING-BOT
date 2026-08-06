from __future__ import annotations

from core.metrics.metrics import InMemoryMetrics


def test_increment_accumulates() -> None:
    metrics = InMemoryMetrics()
    metrics.increment("orders.submitted")
    metrics.increment("orders.submitted", value=2.0)

    assert metrics.snapshot()["counters"]["orders.submitted"] == 3.0


def test_tags_create_distinct_series() -> None:
    metrics = InMemoryMetrics()
    metrics.increment("orders.submitted", tags={"symbol": "EURUSD"})
    metrics.increment("orders.submitted", tags={"symbol": "GBPUSD"})

    counters = metrics.snapshot()["counters"]
    assert counters["orders.submitted[symbol=EURUSD]"] == 1.0
    assert counters["orders.submitted[symbol=GBPUSD]"] == 1.0


def test_observe_and_gauge() -> None:
    metrics = InMemoryMetrics()
    metrics.observe("fill.slippage", 0.4)
    metrics.observe("fill.slippage", 0.6)
    metrics.gauge("account.equity", 10_000.0)

    snapshot = metrics.snapshot()
    assert snapshot["histograms"]["fill.slippage"] == [0.4, 0.6]
    assert snapshot["gauges"]["account.equity"] == 10_000.0
