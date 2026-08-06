from __future__ import annotations

from benchmarks import backtest_engine_benchmark, event_bus_benchmark, signal_fusion_benchmark


async def test_event_bus_benchmark_delivers_every_event_with_no_drops() -> None:
    results = await event_bus_benchmark.run()

    assert len(results) == 4
    for result in results:
        assert result.event_count > 0
        assert result.events_per_second > 0


async def test_backtest_engine_benchmark_runs_the_full_pipeline() -> None:
    result = await backtest_engine_benchmark.run(bar_count=200)

    assert result.bar_count == 200
    assert result.bars_per_second > 0
    assert result.order_count >= 0


def test_signal_fusion_benchmark_evaluates_the_full_module_roster() -> None:
    result = signal_fusion_benchmark.run(bar_count=150, window_size=20)

    assert result.evaluation_count == 130
    assert result.evaluations_per_second > 0
    assert result.mean_latency_ms >= 0
    assert result.p95_latency_ms >= result.median_latency_ms
