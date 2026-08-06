"""Throughput benchmark for the backtest Execution Engine.

Drives a full, realistically wired pipeline -- Strategy -> Risk -> Sizing ->
RiskGatedExecutionEngine -> BacktestExecutionEngine, exactly as assembled in
tests/integration/test_strategy_engine_backtest_live_parity.py -- through a
large synthetic random-walk price series, and reports bars/sec.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.execution.risk_gate import RiskGatedExecutionEngine
from core.interfaces.events import AccountStateChanged, BarClosed, TickReceived
from core.interfaces.types import AccountState, Bar, Symbol, Tick, Timeframe
from core.portfolio.engine import PortfolioEngine
from core.portfolio.position_manager import PositionManager
from core.risk.engine import RiskEngine
from core.risk.sizing import FixedVolumeSizingModel
from core.strategy.engine import StrategyEngine
from execution_backends.backtest.engine import BacktestExecutionEngine
from strategies.simple.sma_crossover import SmaCrossoverStrategy

_SYMBOL = Symbol(name="EURUSD")
_SPREAD = 0.0002


@dataclass(frozen=True, slots=True)
class BacktestBenchmarkResult:
    bar_count: int
    order_count: int
    elapsed_seconds: float

    @property
    def bars_per_second(self) -> float:
        return self.bar_count / self.elapsed_seconds if self.elapsed_seconds > 0 else float("inf")


def _synthetic_closes(bar_count: int, *, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.0, scale=0.0005, size=bar_count)
    closes = 1.1000 + np.cumsum(steps)
    return [float(c) for c in closes]


async def run(bar_count: int = 20_000) -> BacktestBenchmarkResult:
    closes = _synthetic_closes(bar_count)
    event_bus = EventBus()
    order_manager = OrderManager(event_bus)
    position_manager = PositionManager(order_manager, event_bus)
    portfolio = PortfolioEngine(position_manager)
    risk_engine = RiskEngine(
        portfolio, event_bus, max_open_positions=1_000, daily_loss_limit=1e9
    )
    execution_engine = BacktestExecutionEngine(event_bus)
    gated_engine = RiskGatedExecutionEngine(execution_engine, risk_engine, event_bus)
    strategy = SmaCrossoverStrategy(fast_period=5, slow_period=20)
    StrategyEngine(strategy, risk_engine, FixedVolumeSizingModel(0.1), gated_engine, event_bus)

    await event_bus.publish(
        AccountStateChanged(
            account_state=AccountState(
                balance=1_000_000.0,
                equity=1_000_000.0,
                margin=0.0,
                free_margin=1_000_000.0,
                margin_level=None,
                currency="USD",
            )
        )
    )

    start_time = datetime(2026, 1, 1, tzinfo=UTC)
    start = time.perf_counter()
    for i, close in enumerate(closes):
        timestamp = start_time + timedelta(minutes=i)
        await event_bus.publish(
            TickReceived(
                tick=Tick(
                    symbol=_SYMBOL,
                    timestamp=timestamp,
                    bid=close - _SPREAD / 2,
                    ask=close + _SPREAD / 2,
                )
            )
        )
        await event_bus.publish(
            BarClosed(
                bar=Bar(
                    symbol=_SYMBOL,
                    timeframe=Timeframe.M1,
                    timestamp=timestamp,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=0.0,
                )
            )
        )
    elapsed = time.perf_counter() - start

    return BacktestBenchmarkResult(
        bar_count=bar_count, order_count=len(order_manager.list_orders()), elapsed_seconds=elapsed
    )


if __name__ == "__main__":
    result = asyncio.run(run())
    print(
        f"backtest engine: {result.bars_per_second:,.0f} bars/sec "
        f"({result.bar_count:,} bars, {result.order_count} orders, "
        f"{result.elapsed_seconds * 1000:.1f} ms total)"
    )
