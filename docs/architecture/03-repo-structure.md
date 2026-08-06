# Monorepo Structure

Enforces the dependency rule from `02-system-architecture.md`: arrows point inward
only. `core/` imports nothing from any other top-level package.

```
.
├── core/                       # The Trading Kernel — zero outward dependencies
│   ├── event_bus/              # Typed pub/sub, async dispatch
│   ├── kernel/                 # Bootstrap, lifecycle, dependency injection container
│   ├── interfaces/             # Protocols/ports: Connector, ExecutionEngine, Strategy,
│   │                           #   Indicator, RiskModel, SizingModel, DataProvider, Plugin
│   ├── market_data/             # Market Data Engine, canonical Tick/Bar types
│   ├── indicators/              # Indicator Engine (built-ins + registry)
│   ├── signal/                  # Signal Engine, Evidence type, Signal Fusion
│   ├── strategy/                # Strategy Engine, Alpha/Portfolio/Execution/Risk model contracts
│   ├── portfolio/                # Portfolio Engine, Position Manager, CQRS commands/queries
│   ├── risk/                     # Risk Engine, kill switch, exposure/correlation/drawdown checks
│   ├── execution/                # Order Manager, Execution Engine interface, order state machine
│   ├── config/                   # Configuration System (schemas, layered loader)
│   ├── logging/                  # Structured logging, correlation IDs
│   ├── metrics/                  # Metrics System
│   └── plugin_manager/            # Plugin discovery/registration/DI
│
├── connectors/                  # Venue adapters — MT4/MT5 only, but interface-generic
│   ├── mt_common/                # Shared MT4/MT5 protocol: message schema, reconnect logic,
│   │                             #   symbol/timeframe normalization, fault-tolerant transport
│   ├── mt4/                       # MT4-specific bridge (DLL/socket EA side) + Python adapter
│   ├── mt5/                       # MT5-specific bridge (Python API + optional socket bridge)
│   └── transport/                 # ZeroMQ / TCP / WebSocket / Named Pipes transport backends
│
├── execution_backends/           # ExecutionEngine implementations
│   ├── backtest/                  # Simulated fills, slippage/commission/swap/latency models
│   ├── paper/                      # Paper trading against live MT5 quotes, simulated fills
│   └── live/                       # Live execution via connectors/mt5, connectors/mt4
│
├── strategies/                    # User/plugin strategy implementations (no core changes needed)
│   ├── simple/                     # init()/next()-style rule-based strategies
│   └── composed/                    # Full Alpha/Portfolio/Execution/Risk model strategies
│
├── quant/                          # Quantitative research layer (feeds Signal Engine as plugins)
│   ├── statistics/                  # Descriptive/inferential/Bayesian/hypothesis tests
│   ├── math_models/                  # Linear algebra, Kalman/particle filters, HMM, FFT/wavelet
│   ├── technical_analysis/            # Trend/momentum/volume/volatility indicator libraries
│   ├── price_action/                   # Market structure, SMC, order blocks, FVGs, BOS/CHOCH
│   ├── fibonacci/                       # Retracement/extension/time-zone/cluster/heatmap engine
│   ├── elliott_wave/                     # Wave counting, multi-hypothesis ranking
│   ├── harmonics/                         # Gartley/Bat/Crab/... pattern detection + scoring
│   ├── candlesticks/                       # Candlestick pattern recognition + statistical scoring
│   ├── chart_patterns/                      # H&S, double top/bottom, triangles, etc. + targets
│   └── fusion/                               # Signal Fusion: Evidence aggregation, confidence scoring
│
├── backtesting/                    # Backtesting Engine orchestration (uses execution_backends/backtest)
│   ├── engine/                       # Event replay driver, multi-threaded run orchestration
│   ├── walk_forward/                  # Walk-forward window generation and evaluation
│   └── validation/                     # Monte Carlo, bootstrap, overfitting/look-ahead-bias checks
│
├── optimization/                    # Optimization Engine
│   ├── algorithms/                    # Grid, random, Bayesian, genetic, PSO, multi-objective
│   └── distributed/                    # Parallel/distributed run coordination
│
├── machine_learning/                 # ML Engine
│   ├── features/                       # Feature extraction shared with quant/ layers
│   ├── models/                          # Model training/inference wrappers
│   └── ai_assistant/                     # LLM-based strategy review/overfitting detection/docs
│
├── analytics/                        # Analytics Engine (Sharpe, Sortino, VaR, etc. — pluggable)
├── reporting/                        # Reporting Engine (renders analytics + Evidence trails)
├── notifications/                     # Notification System (email/Slack/Telegram/webhook adapters)
├── database/                          # Database Layer: repository interfaces + backends
│   ├── repositories/                    # TickRepository, OrderRepository, PositionRepository...
│   └── backends/                         # Postgres/Timescale, Parquet/PyArrow implementations
│
├── plugins/                            # Third-party/user plugins living outside core, per Plugin Manager
├── examples/                            # Example strategies, example connector configs
├── tests/
│   ├── unit/                             # Mirrors package structure 1:1
│   ├── integration/                       # Cross-engine tests (e.g. signal -> risk -> execution)
│   └── benchmarks/                         # Performance benchmarks per engine
└── docs/
    ├── architecture/                       # This document set
    ├── adr/                                 # Architecture Decision Records
    └── api/                                  # Generated interface/API reference
```

## Rules enforced in CI

1. **Import direction lint**: `core/` may not import from `connectors/`,
   `execution_backends/`, `strategies/`, `quant/`, `backtesting/`, `optimization/`,
   `machine_learning/`, `database/`, `plugins/`. Violation fails the build.
2. **No circular imports** across any top-level package, checked via dependency graph
   analysis in CI, not just at review time.
3. **Every `core/interfaces/*` Protocol must have at least one concrete implementation
   under `execution_backends/` or `connectors/` covered by an integration test** —
   prevents interfaces from drifting out of sync with reality.
4. Package boundaries above map 1:1 to Python packages with their own `pyproject.toml`
   in a workspace (uv/poetry workspaces), so each can also be versioned and tested in
   isolation, not just organized by folder convention.
