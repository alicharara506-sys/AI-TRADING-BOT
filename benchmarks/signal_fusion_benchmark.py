"""Latency benchmark for core.signal.engine.SignalEngine.evaluate().

Registers the full quant module roster (the same set proven to compose
together in tests/integration/test_quant_module_roster_signal_fusion.py) and
times evaluate() across a rolling window of a large synthetic price series,
reporting mean/median/p95 latency and evaluations/sec.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from core.interfaces.types import Bar, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from quant.candlesticks.patterns import EngulfingPatternModule
from quant.fibonacci.confluence import FibonacciConfluenceModule
from quant.price_action.structure import MarketStructureModule
from quant.statistics.mean_reversion import AdfMeanReversionModule
from quant.technical_analysis.volatility import AtrVolatilityBreakoutModule
from quant.technical_analysis.volume import OnBalanceVolumeModule

_SYMBOL = Symbol(name="EURUSD")


@dataclass(frozen=True, slots=True)
class SignalFusionBenchmarkResult:
    evaluation_count: int
    window_size: int
    elapsed_seconds: float
    mean_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float

    @property
    def evaluations_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return float("inf")
        return self.evaluation_count / self.elapsed_seconds


def _synthetic_bars(bar_count: int, *, seed: int = 0) -> list[Bar]:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.0, scale=0.0005, size=bar_count)
    closes = 1.1000 + np.cumsum(steps)
    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    for i, close in enumerate(closes):
        wobble = abs(float(rng.normal(0.0, 0.0002)))
        bars.append(
            Bar(
                symbol=_SYMBOL,
                timeframe=Timeframe.M1,
                timestamp=start_time + timedelta(minutes=i),
                open=float(close) - wobble,
                high=float(close) + wobble,
                low=float(close) - wobble,
                close=float(close),
                volume=1.0,
            )
        )
    return bars


def _build_engine() -> SignalEngine:
    engine = SignalEngine(SignalFusion(threshold=0.6))
    engine.register_module(AdfMeanReversionModule(window=30))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))
    engine.register_module(EngulfingPatternModule())
    engine.register_module(MarketStructureModule(swing_arm=2))
    engine.register_module(OnBalanceVolumeModule(lookback=10))
    engine.register_module(AtrVolatilityBreakoutModule(period=14))
    return engine


def run(bar_count: int = 2_000, window_size: int = 100) -> SignalFusionBenchmarkResult:
    bars = _synthetic_bars(bar_count)
    engine = _build_engine()

    latencies_seconds: list[float] = []
    start = time.perf_counter()
    for i in range(window_size, bar_count):
        context = MarketContext(symbol=_SYMBOL, bars=tuple(bars[i - window_size : i]))
        call_start = time.perf_counter()
        engine.evaluate(context)
        latencies_seconds.append(time.perf_counter() - call_start)
    elapsed = time.perf_counter() - start

    latencies_ms = [s * 1000 for s in latencies_seconds]
    return SignalFusionBenchmarkResult(
        evaluation_count=len(latencies_ms),
        window_size=window_size,
        elapsed_seconds=elapsed,
        mean_latency_ms=statistics.mean(latencies_ms),
        median_latency_ms=statistics.median(latencies_ms),
        p95_latency_ms=sorted(latencies_ms)[int(len(latencies_ms) * 0.95)],
    )


if __name__ == "__main__":
    result = run()
    print(
        f"signal fusion: {result.evaluations_per_second:,.0f} evaluations/sec "
        f"(window={result.window_size}, mean={result.mean_latency_ms:.3f} ms, "
        f"median={result.median_latency_ms:.3f} ms, p95={result.p95_latency_ms:.3f} ms, "
        f"{result.evaluation_count:,} evaluations in {result.elapsed_seconds:.2f}s)"
    )
