from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backtesting.validation.look_ahead import LookAheadBiasCheck
from backtesting.validation.monte_carlo import MonteCarloCheck
from backtesting.validation.pipeline import ValidationPipeline
from backtesting.validation.walk_forward import WalkForwardCheck
from core.event_bus.bus import EventBus
from core.execution.manager import OrderManager
from core.execution.risk_gate import RiskGatedExecutionEngine
from core.execution.validation_gate import ValidationGatedExecutionEngine
from core.interfaces.connector import Connector
from core.interfaces.events import AccountStateChanged
from core.interfaces.strategy import Strategy
from core.interfaces.types import Bar, Symbol, Timeframe
from core.interfaces.validation import ValidationReport
from core.portfolio.engine import PortfolioEngine
from core.portfolio.position_manager import PositionManager
from core.risk.engine import RiskEngine
from core.risk.sizing import FixedVolumeSizingModel
from core.strategy.engine import StrategyEngine
from execution_backends.live.engine import LiveExecutionEngine
from live_trading.flip_safe_execution import FlipSafeExecutionEngine
from live_trading.preflight import run_preflight_backtest
from strategies.simple.sma_crossover import SmaCrossoverStrategy


@runtime_checkable
class HistoricalConnector(Connector, Protocol):
    """A Connector that can also stream live bars/ticks in the background and
    report closed historical bars -- what LiveRunner needs to both pre-flight
    validate a strategy and then run it live against the same venue.
    MT5Connector satisfies this structurally (connectors/mt5/connector.py);
    MT4Connector does not have get_historical_bars yet, so LiveRunner is
    MT5-only for now.
    """

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def get_historical_bars(
        self, symbol: Symbol, timeframe: Timeframe, count: int
    ) -> list[Bar]: ...


@dataclass(frozen=True, slots=True)
class LiveRunnerConfig:
    symbol: Symbol
    timeframe: Timeframe
    fast_period: int = 5
    slow_period: int = 20
    volume: float = 0.01
    # Must be >= 2 for a flip-only strategy: RiskEngine evaluates a flip's
    # *closing* signal while the position being closed is still open in its
    # own ledger, so a limit of 1 would veto every flip after the first
    # trade. See live_trading/preflight.py::run_preflight_backtest for the
    # same constraint applied to the pre-flight backtest's Risk Engine.
    max_open_positions: int = 2
    daily_loss_limit: float = 100.0
    history_bar_count: int = 2000
    account_poll_interval_seconds: float = 30.0


class LiveRunnerError(Exception):
    pass


class LiveRunner:
    """Ties a real MT5Connector to a Strategy (SmaCrossoverStrategy by
    default) through every gate docs/runbook/backtest-to-live.md requires: a
    pre-flight backtest against this account's own real history run through
    the Validation Pipeline first (run_forever() will not construct a live
    order path at all if that report doesn't pass), then the platform's
    normal Risk Engine and Strategy Engine wiring, with
    FlipSafeExecutionEngine closing any stale opposite position first for
    accounts in hedging mode.
    """

    def __init__(
        self,
        connector: HistoricalConnector,
        config: LiveRunnerConfig,
        event_bus: EventBus,
        *,
        strategy_factory: Callable[[], Strategy] | None = None,
        strategy_name: str | None = None,
        pipeline: ValidationPipeline | None = None,
    ) -> None:
        self._connector = connector
        self._config = config
        self._event_bus = event_bus
        self._strategy_factory = strategy_factory or self._default_strategy_factory
        self._strategy_name = strategy_name or SmaCrossoverStrategy.strategy_name
        self._pipeline = pipeline or ValidationPipeline(
            walk_forward=WalkForwardCheck(max_degradation=0.5),
            monte_carlo=MonteCarloCheck(max_drawdown=30.0, iterations=500, seed=1),
            look_ahead=LookAheadBiasCheck(),
        )
        self._running = False

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    def _default_strategy_factory(self) -> SmaCrossoverStrategy:
        return SmaCrossoverStrategy(
            fast_period=self._config.fast_period, slow_period=self._config.slow_period
        )

    async def preflight(self) -> tuple[ValidationReport, list[float]]:
        bars = await self._connector.get_historical_bars(
            self._config.symbol, self._config.timeframe, self._config.history_bar_count
        )
        account = await self._connector.get_account_state()
        return await run_preflight_backtest(
            self._strategy_factory,
            bars,
            strategy_name=self._strategy_name,
            starting_equity=account.equity,
            sizing_model=FixedVolumeSizingModel(self._config.volume),
            pipeline=self._pipeline,
            max_open_positions=self._config.max_open_positions,
        )

    async def run_forever(
        self,
        *,
        on_preflight_complete: Callable[[ValidationReport, list[float]], None] | None = None,
    ) -> ValidationReport:
        if not self._connector.is_connected():
            await self._connector.connect()

        report, trade_returns = await self.preflight()
        if on_preflight_complete is not None:
            on_preflight_complete(report, trade_returns)
        if not report.passed:
            raise LiveRunnerError(
                f"Refusing to trade live: validation failed ({report.failure_summary()}) "
                f"against {len(trade_returns)} trades observed in real history."
            )

        order_manager = OrderManager(self._event_bus)
        position_manager = PositionManager(order_manager, self._event_bus)
        portfolio = PortfolioEngine(position_manager)
        risk_engine = RiskEngine(
            portfolio,
            self._event_bus,
            max_open_positions=self._config.max_open_positions,
            daily_loss_limit=self._config.daily_loss_limit,
        )

        live_engine = LiveExecutionEngine(self._connector, self._event_bus)
        flip_safe_engine = FlipSafeExecutionEngine(self._connector, live_engine)
        validated_engine = ValidationGatedExecutionEngine(flip_safe_engine, report)
        risk_gated_engine = RiskGatedExecutionEngine(validated_engine, risk_engine, self._event_bus)

        strategy = self._strategy_factory()
        StrategyEngine(
            strategy,
            risk_engine,
            FixedVolumeSizingModel(self._config.volume),
            risk_gated_engine,
            self._event_bus,
        )

        await self._connector.start()
        await self._connector.subscribe_ticks(self._config.symbol)
        await self._connector.subscribe_bars(self._config.symbol, self._config.timeframe)

        self._running = True
        try:
            while self._running:
                account = await self._connector.get_account_state()
                await self._event_bus.publish(AccountStateChanged(account_state=account))
                if risk_engine.is_kill_switch_engaged():
                    break
                if not self._running:
                    break
                await asyncio.sleep(self._config.account_poll_interval_seconds)
        finally:
            self._running = False
            await self._connector.stop()

        return report

    def stop(self) -> None:
        self._running = False


__all__ = ["HistoricalConnector", "LiveRunner", "LiveRunnerConfig", "LiveRunnerError"]
