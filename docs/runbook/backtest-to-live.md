# Runbook: taking a strategy from backtest to a live MT4/MT5 account

This walks through the same pipeline the integration tests prove, in the
order an operator actually runs it. Every class named below is real --
follow the links to the exact file if you want the full signature.

## 1. Write the strategy

Implement the `Strategy` Protocol (`core/interfaces/strategy.py`) or extend
an existing one -- e.g. `strategies/simple/sma_crossover.py`'s
`SmaCrossoverStrategy`. A strategy consumes `MarketContext` and emits at
most one `Direction` per call; it does not know about risk, sizing, or
which venue it's running against.

## 2. Backtest it

Wire the strategy through `core.strategy.engine.StrategyEngine` against
`execution_backends.backtest.engine.BacktestExecutionEngine`, replaying
historical bars from `core.market_data.replay.ParquetBarReplayProvider` (or
any `DataProvider`). This is the same wiring proven in
[`tests/integration/test_strategy_engine_backtest_live_parity.py`](../../tests/integration/test_strategy_engine_backtest_live_parity.py):

```python
event_bus = EventBus()
order_manager = OrderManager(event_bus)
position_manager = PositionManager(order_manager, event_bus)
portfolio = PortfolioEngine(position_manager)
risk_engine = RiskEngine(portfolio, event_bus, max_open_positions=10, daily_loss_limit=1_000.0)
execution_engine = BacktestExecutionEngine(event_bus)
gated_engine = RiskGatedExecutionEngine(execution_engine, risk_engine, event_bus)
StrategyEngine(strategy, risk_engine, FixedVolumeSizingModel(0.1), gated_engine, event_bus)
# publish AccountStateChanged, then BarClosed/TickReceived for each historical bar
```

Collect the resulting per-trade returns from `order_manager.list_orders()` /
your fill events -- that trade-return sequence is the input to every
following step.

## 3. Compute performance metrics and generate a report

```python
from reporting.performance_report import PerformanceReport

report = PerformanceReport.from_returns("my_strategy", trade_returns)
print(report.render())
```

`PerformanceReport` wraps the full metrics suite in `analytics/metrics.py`
(Sharpe, Sortino, Calmar, max drawdown, profit factor, expectancy, SQN,
VaR/CVaR). There is no hardcoded threshold here for "good enough" -- that
judgment belongs to the operator and the Validation Pipeline in the next
step, not to this report.

## 4. Run the Validation Pipeline -- this gate is not optional

```python
from backtesting.validation.look_ahead import LookAheadBiasCheck
from backtesting.validation.monte_carlo import MonteCarloCheck
from backtesting.validation.pipeline import ValidationPipeline
from backtesting.validation.walk_forward import WalkForwardCheck

pipeline = ValidationPipeline(
    walk_forward=WalkForwardCheck(max_degradation=0.5),
    monte_carlo=MonteCarloCheck(max_drawdown=30.0, iterations=500, seed=1),
    look_ahead=LookAheadBiasCheck(),
)
report = pipeline.run(
    strategy_name="my_strategy", trade_returns=trade_returns, bar_timestamps=timestamps
)
```

`report.passed` is `True` only if walk-forward, Monte Carlo, and
look-ahead-bias checks all pass. This report is not advisory -- the next
step's `ValidationGatedExecutionEngine` cannot be constructed at all with a
failing report (`core/execution/validation_gate.py` raises
`ValidationError` in `__init__`), so there is no code path that
accidentally skips this gate.

## 5. Connect to the live venue

Choose MT5 or MT4:

- **MT5**: construct `connectors.mt5.connector.MT5Connector` with the real
  `MetaTrader5` module (implements the `MT5Api` Protocol) and your account
  `login`/`password`/`server`. Load credentials from `KERNEL_*` environment
  variables via `core/config/settings.py` or a gitignored local file --
  never a file intended to be committed (see
  [`docs/security/phase-14-review.md`](../security/phase-14-review.md)).
  Before wiring up a full strategy, verify the connector against your real
  terminal with
  [`scripts/manual/mt5_connectivity_check.py`](../../scripts/manual/mt5_connectivity_check.py)
  -- a read-only connect/account-state/symbol-info check that places no
  orders. It must run on the same Windows machine as the terminal itself.
- **MT4**: construct `connectors.mt4.connector.MT4Connector` with a
  `ZmqRequester`/`ZmqSubscriber` pointed at the companion MQL4 EA's bound
  addresses. **Run this on a private network segment** -- the ZeroMQ
  command channel has no authentication (see the security review's MT4
  finding) -- localhost, a VPN, or an SSH tunnel, never a publicly
  reachable address.

Call `await connector.connect()`, then `await connector.start()` (MT5) or
run `connector.listen()` as a background task (MT4) to begin streaming
ticks/bars onto the same `EventBus`.

## 6. Wrap live execution with both gates

```python
live_engine = LiveExecutionEngine(connector, event_bus)
validated_engine = ValidationGatedExecutionEngine(live_engine, report)
risk_gated_engine = RiskGatedExecutionEngine(validated_engine, risk_engine, event_bus)
StrategyEngine(strategy, risk_engine, sizing_model, risk_gated_engine, event_bus)
```

This is the exact same `strategy` object used in backtesting, unmodified --
that's what backtest/live parity means in this codebase. Only the
`ExecutionEngine` and data source changed.

### Automated version of steps 4-6: `live_trading.runner.LiveRunner`

[`live_trading/runner.py`](../../live_trading/runner.py) automates this
whole sequence for `SmaCrossoverStrategy` against a real MT5 account:
`LiveRunner.preflight()` fetches the account's own real historical bars
(`MT5Connector.get_historical_bars`), replays them through
`live_trading.preflight.run_preflight_backtest` (the same
`BacktestExecutionEngine` + Validation Pipeline wiring as steps 2-4 above),
and `run_forever()` refuses to construct the live execution path at all if
that report doesn't pass -- there is no separate step to remember to run.
The live path itself wraps `LiveExecutionEngine` with
`live_trading.flip_safe_execution.FlipSafeExecutionEngine`, which closes any
existing opposite-side position before a flip signal opens a new one:
required because an MT5 hedging account (`AccountMode.HEDGING`) opens a
second, independent position for an opposite-side order instead of netting
it the way the kernel's own simulated `PositionManager` does.
[`scripts/manual/run_live_strategy.py`](../../scripts/manual/run_live_strategy.py)
is the runnable entry point, configured entirely by environment variables
(see its docstring); like the connectivity check, it must run on the same
Windows machine as the terminal.

## 7. Monitor

Configure a `Notifier` (`notifications/notifier.py`) -- `LoggingNotifier`
for structured logs, or `WebhookNotifier` for Slack/Telegram/PagerDuty --
and send `PerformanceReport.render()` output on whatever cadence you want
(e.g. on every closed trade, or on a timer). The
`HistoricalHitRateStore` (`analytics/hit_rate_store.py`) can be wired into
pattern-based `AnalysisModule`s (see `EngulfingPatternModule`) so their
Evidence confidence shifts from a geometric estimate to a real empirical
win rate once enough live outcomes have been recorded.

## Chaos-tolerance expectations

Both connectors now flip `is_connected()` to `False` and publish
`ConnectionStateChanged(LOST)` the moment any underlying API/socket call
fails -- they do not leave stale state around. Neither connector
auto-retries an order submission on failure (to avoid a duplicate-order
risk from blind retries) -- a failed `submit_order` call is a signal for
the operator's own supervision logic to reconnect and decide, not something
this layer silently papers over. See
[`tests/integration/test_connector_fault_tolerance.py`](../../tests/integration/test_connector_fault_tolerance.py)
for the exact failure/recovery behavior each connector guarantees.
