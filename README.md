# AI Trading Bot — institutional-grade MT4/MT5 quantitative trading platform

An event-driven, hexagonal-architecture quantitative trading system for
MetaTrader 4 and MetaTrader 5. Built from first principles -- inspired by,
but never merged from, eight reference open-source projects (NautilusTrader,
QuantConnect LEAN, StockSharp, Backtrader, backtesting.py, EA31337,
exchange-api, QuantDinger) -- across 14 independently-shippable phases, each
with concrete, empirically-verified exit criteria.

304 tests, `mypy --strict` clean across 120 source files, `ruff` clean, and
an enforced import-direction rule that keeps `core/` free of outward
dependencies on any connector, engine, or strategy package.

## Architecture at a glance

- **Hexagonal / Ports & Adapters.** `core/` defines the domain and every
  Protocol (`Connector`, `ExecutionEngine`, `DataProvider`, `AnalysisModule`,
  ...); everything else is an adapter plugged in through those Protocols.
  `scripts/check_import_direction.py` enforces this in CI -- `core/` cannot
  import from `connectors/`, `execution_backends/`, `strategies/`, `quant/`,
  `backtesting/`, `optimization/`, or `machine_learning/`.
- **Event-driven core.** A single typed async `EventBus`
  (`core/event_bus/bus.py`) carries every domain event (ticks, bars, order
  lifecycle, connection state, signals) between engines. Structural
  enforcement, not advisory: `RiskGatedExecutionEngine` and
  `ValidationGatedExecutionEngine` make illegal states unconstructable --
  a vetoed order or an unvalidated strategy cannot reach a live venue by
  construction, not by convention.
- **Backtest/live parity.** The same `Strategy`, `Signal`, `Risk`, and
  `Portfolio` code runs unmodified against `BacktestExecutionEngine` or
  `LiveExecutionEngine` -- only the venue and data source differ. Proven in
  `tests/integration/test_strategy_engine_backtest_live_parity.py`.
- **Evidence/Signal Fusion explainability.** Every `AnalysisModule` (ADF
  mean-reversion, Fibonacci confluence, candlestick patterns, BOS/CHOCH
  market structure, OBV, ATR breakout, a calibrated ML classifier, ...)
  emits `Evidence` with a rationale; `SignalFusion` combines evidence via
  log-odds summation (not naive averaging), and every resulting
  `TradeSignal` is queryable and has an `.explain()`.
- **MT5 via an injected `MT5Api` Protocol** (the real `MetaTrader5` package
  is Windows-only, so it's mirrored, not imported, letting the connector run
  and test on any platform). **MT4 via a thin ZeroMQ client** (REQ/REP for
  commands, PUB/SUB for streaming) talking to a companion MQL4 Expert
  Advisor that is a "thin forwarder only" -- no decision logic in the EA.

See [`docs/architecture/00-overview.md`](docs/architecture/00-overview.md)
for the full design document set, and
[`docs/architecture/07-roadmap.md`](docs/architecture/07-roadmap.md) for how
the 14 build phases map onto the codebase below.

## Repository layout

| Package | Responsibility |
| --- | --- |
| `core/` | Domain types, events, Protocols, Event Bus, DI kernel, config, logging, execution/risk/portfolio/signal engines |
| `connectors/mt5/`, `connectors/mt4/` | MetaTrader connector implementations |
| `connectors/mt_common/`, `connectors/transport/` | Shared reconnect/heartbeat/symbol-mapping logic and the ZeroMQ transport primitives |
| `execution_backends/backtest/`, `execution_backends/live/` | The two `ExecutionEngine` implementations that give backtest/live parity |
| `strategies/` | Strategy implementations (e.g. `SmaCrossoverStrategy`) |
| `quant/` | The quant research library: statistics, Fibonacci, candlesticks, price action/market structure, technical analysis |
| `machine_learning/` | Feature pipeline, calibrated classifier, `AIReviewer` |
| `backtesting/validation/` | The mandatory Strategy Validation Pipeline (walk-forward, Monte Carlo, look-ahead bias) |
| `optimization/` | Grid/Random search with an in-sample/out-of-sample overfitting guard |
| `analytics/` | Risk/performance metrics suite and the historical hit-rate store |
| `reporting/`, `notifications/` | `PerformanceReport` and the `Notifier` Protocol (logging + webhook) |
| `benchmarks/` | Throughput/latency benchmarks for the Event Bus, backtest engine, and Signal Fusion (`docs/benchmarks/results.md`) |
| `tests/support/` | Reusable test doubles: `FakeConnector`, `FakeMT4Terminal`, `FakeMT5Api`, `RecordingHttpServer` |
| `scripts/` | `check_import_direction.py`, the CI-enforced dependency-rule linter |

## Getting started

```bash
python3 -m pip install -e ".[dev]"

python3 -m pytest -q                # 304 tests
python3 -m ruff check .
python3 -m mypy core connectors execution_backends strategies quant \
  backtesting optimization machine_learning analytics reporting \
  notifications benchmarks
python3 scripts/check_import_direction.py
```

Run the benchmark suite:

```bash
python3 -m benchmarks.run_all
```

## Where to look for a working example

Rather than a standalone example script that can drift out of sync with the
real code, the canonical "how does this all wire together" reference is the
integration test suite -- every phase's exit criteria is proven there
against real (not mocked) components:

- [`tests/integration/test_strategy_engine_backtest_live_parity.py`](tests/integration/test_strategy_engine_backtest_live_parity.py) --
  full signal -> risk -> sizing -> execution pipeline, backtest and live.
- [`tests/integration/test_quant_module_roster_signal_fusion.py`](tests/integration/test_quant_module_roster_signal_fusion.py) --
  the full quant module roster composing through Signal Fusion.
- [`tests/integration/test_validation_gate_enforcement.py`](tests/integration/test_validation_gate_enforcement.py) --
  a strategy cannot go live without a passing Validation Report.
- [`tests/integration/test_connector_fault_tolerance.py`](tests/integration/test_connector_fault_tolerance.py) --
  MT4/MT5 chaos tests: simulated API/socket failures and genuine recovery.
- [`docs/runbook/backtest-to-live.md`](docs/runbook/backtest-to-live.md) --
  the operator-facing walkthrough of taking a strategy from backtest to a
  live MT5/MT4 account.

## Security

See [`docs/security/phase-14-review.md`](docs/security/phase-14-review.md)
for the credential-handling, input-validation, and dependency-audit review,
including the most significant open item: the MT4 ZeroMQ command/market-data
channel has no authentication or encryption and must be run on a private
network segment.
