# Unified System Architecture

Codename for internal reference: **Kernel** (the platform core) + **Forge** (the MT4/MT5
connector family). Names are placeholders, not a commitment.

## 1. Architectural style

- **Hexagonal / Ports & Adapters** at the outermost level: the Trading Kernel is the
  application core; MT4, MT5, databases, notification channels, and dashboards are all
  adapters plugged into ports the kernel defines. The kernel never imports an adapter.
- **Event-driven core**: all cross-engine communication is asynchronous messages on an
  **Event Bus**, not direct calls. Engines publish typed events and subscribe to typed
  events. This is what makes backtest and live share one code path (per the
  NautilusTrader/LEAN analysis) — a `BacktestExecutionEngine` and a
  `MT5ExecutionEngine` both consume `OrderSubmitted` events and both emit
  `OrderFilled` events; nothing upstream knows which one is running.
- **Dependency rule**: dependencies point inward only. `core` depends on nothing else
  in the repo. `connectors/*`, `database/*`, `strategies/*` depend on `core`'s
  interfaces. Nothing in `core` imports from `connectors`, `database`, or `strategies`.
  Enforced by lint rule (import-linter / custom CI check), not convention alone.
- **CQRS at the portfolio boundary**: commands (`SubmitOrder`, `ClosePosition`) and
  queries (`GetOpenPositions`, `GetEquityCurve`) go through separate interfaces on the
  Portfolio Engine, so read-heavy consumers (dashboards, analytics) never block or
  race with the write path (order/position mutation).

## 2. The Trading Kernel — core engines

Each engine is a bounded context behind an interface (`Protocol` in Python terms).
No engine holds a reference to another engine's concrete class — only to the Event
Bus and to narrow query interfaces it's explicitly given.

```
                                 ┌─────────────────────┐
                                 │      Event Bus       │
                                 │ (typed pub/sub, async)│
                                 └───────────┬──────────┘
        ┌──────────────┬──────────────┬──────┴───────┬──────────────┬─────────────┐
        │              │              │              │              │             │
 ┌──────▼─────┐ ┌──────▼─────┐ ┌──────▼──────┐┌──────▼──────┐┌──────▼─────┐┌──────▼──────┐
 │Market Data  │ │  Signal    │ │  Strategy    ││  Portfolio  ││   Risk     ││  Execution   │
 │  Engine     │ │  Engine    │ │  Engine      ││   Engine    ││   Engine   ││   Engine     │
 └──────┬─────┘ └──────┬─────┘ └──────┬──────┘└──────┬──────┘└──────┬─────┘└──────┬──────┘
        │              │              │              │              │             │
        │       ┌──────▼──────┐ ┌─────▼──────┐┌──────▼──────┐       │      ┌──────▼──────┐
        │       │  Indicator  │ │  Position   ││Order Manager│       │      │  Connector   │
        │       │  Engine     │ │  Manager     ││             │       │      │  (MT4/MT5)   │
        │       └─────────────┘ └─────────────┘└─────────────┘       │      └─────────────┘
        │                                                             │
 ┌──────▼─────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌▼────────────┐
 │Backtesting  │  │ Optimization│  │  Analytics  │  │  Machine    │  │  Plugin      │
 │  Engine     │  │   Engine    │  │   Engine    │  │  Learning   │  │  Manager     │
 └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

Cross-cutting, not shown per-box: **Configuration System**, **Logging Framework**,
**Metrics System**, **Database Layer**, **Reporting Engine**, **Notification System**
— every engine above depends on these five as injected services, never as globals.

### 2.1 Market Data Engine
- Owns tick/OHLC ingestion, normalization, and the canonical time-series buffer type
  (`Bar`, `Tick` — the "Lines"-style uniform buffer from the Backtrader analysis).
  Same buffer type is produced whether the source is a live MT5 tick stream or a
  historical CSV/Parquet file replayed for backtest.
- Publishes `TickReceived`, `BarClosed` events. Nothing downstream (indicators,
  strategies) knows or cares if the source is live or historical.
- Standalone service boundary (per the StockSharp/Hydra analysis): can run and persist
  data independent of whether a strategy is attached.

### 2.2 Indicator Engine
- Pure functions/stateful transforms over the canonical buffer type. One
  implementation, reused identically by live trading, backtesting, optimization, and
  the Analytics/ML engines (explicit requirement — no separate "backtest indicator"
  vs "live indicator").
- Composite/AI-generated/plugin indicators register through the Plugin Manager with a
  single `Indicator` interface: `update(bar) -> value`.

### 2.3 Signal Engine (the quantitative research layer)
- Hosts the multi-layer analysis engine (mathematical, statistical, technical, price
  action/SMC, Fibonacci, Elliott Wave, harmonic patterns, chart patterns — full detail
  in `05-quant-research-engine.md`).
- Every analytical layer emits a typed, weighted **Evidence** object
  (see §4 below), not a trade decision. Evidence objects flow into the fusion layer.
- Signal Fusion (probabilistic decision engine) is a distinct component inside this
  engine: it consumes Evidence from every layer, computes a combined confidence score,
  and only then emits a `TradeSignal` — the first point downstream where "should we
  trade" is decided.

### 2.4 Strategy Engine
- Orchestrates one or more **Strategy** instances, each composed from: a Signal
  source (Signal Engine output, or a simple rule the strategy defines itself),
  position-sizing model, and entry/exit rules.
- Two supported authoring modes, matching the backtesting.py-vs-LEAN spectrum found
  in the repo analysis:
  1. **Simple mode**: `on_bar()`/`on_signal()` callback, for rule-based/simple
     strategies.
  2. **Composed mode**: explicit Alpha Model + Portfolio Construction Model +
     Execution Model + Risk Model, independently swappable (direct descendant of
     LEAN's Algorithm Framework).
- Strategies are loaded through the Plugin Manager and are **hot-swappable**: a
  strategy is a versioned, stateless-between-reloads unit; its state (open positions,
  parameters) lives in the Portfolio/Position Manager, not in the strategy instance,
  so swapping the code doesn't lose live state.

### 2.5 Portfolio Engine + Position Manager
- Single source of truth for positions, balances, equity, exposure — across all
  strategies and symbols. Position Manager tracks per-position state (open, partials,
  hedged legs under MT5 hedging mode); Portfolio Engine aggregates across positions
  for exposure/correlation/drawdown queries.
- CQRS split: `PortfolioCommands` (mutate) vs `PortfolioQueries` (read) as separate
  interfaces, per §1.

### 2.6 Risk Engine
- Subscribes to every `TradeSignal` and every `OrderSubmitted` event **before** they
  reach the Execution Engine, and can veto or resize. This is a hard architectural
  rule: **the Risk Engine sits in the event path, not beside it** — no strategy or
  execution path can bypass it, which is what "risk management must override every
  strategy" requires structurally, not just by convention.
- Owns dynamic position sizing models (Kelly, ATR, volatility-based), exposure limits,
  correlation checks, drawdown/daily-loss limits, and the kill switch.

### 2.7 Order Manager + Execution Engine
- Order Manager: order lifecycle state machine (pending -> submitted -> partially
  filled -> filled/cancelled/rejected), independent of venue.
- Execution Engine: translates internal `Order` objects to venue calls through the
  Connector port, and translates venue events (fills, rejects, requotes) back to
  internal events. The **same Execution Engine interface** has a
  `BacktestExecutionEngine` (simulated fills) and `MT5ExecutionEngine`/
  `MT4ExecutionEngine` (real fills) implementation — this is the load-bearing
  abstraction that makes backtest-live parity possible.

### 2.8 Backtesting Engine, Optimization Engine, ML Engine, Analytics Engine
- Detailed in `06-backtesting-optimization-risk.md`. Architecturally, all three
  consume the exact same Strategy/Signal/Portfolio/Risk engine code as live trading —
  they differ only in which Execution Engine and Market Data source is wired in, and
  in orchestration (single run vs. parameter sweep vs. walk-forward window).

### 2.9 Plugin Manager
- Single registration/discovery mechanism used by every extension point: strategies,
  indicators, risk models, sizing models, data providers, connectors, reports, AI
  modules, optimization algorithms. A plugin is a Python entry-point-registered class
  implementing one of a fixed set of `Protocol` interfaces; the Plugin Manager
  resolves, validates the interface, and injects dependencies (Event Bus, Config,
  Logger) — no plugin imports the kernel's concrete classes.

## 3. Cross-cutting services (all engines depend on these, injected not imported)

- **Configuration System**: layered config (defaults -> environment -> per-strategy
  override), validated against schemas at load time, hot-reloadable where safe.
- **Logging Framework**: structured, correlation-ID-tagged (every event carries a
  trace ID from signal -> order -> fill -> P&L, for the explainability requirement).
- **Metrics System**: every engine emits latency/throughput/error metrics on a
  standard interface (Prometheus-compatible counters/histograms).
- **Database Layer**: repository interfaces (`TickRepository`, `OrderRepository`,
  `PositionRepository`) with swappable backends (Postgres/Timescale for relational +
  time-series, Parquet/PyArrow for bulk historical data).
- **Reporting Engine** and **Notification System**: consume events off the bus like
  any other subscriber; never in the hot path of order execution.

## 4. The Evidence/Explainability contract

Every analytical layer (technical, statistical, Fibonacci, Elliott Wave, harmonic,
SMC, ML) implements one interface and emits one type:

```
Evidence:
  source_module: str            # e.g. "elliott_wave", "harmonic_pattern", "adf_test"
  direction: Long | Short | Neutral
  confidence: float [0..1]
  rationale: dict                # machine-readable: which rule/test fired and why
  supporting_data: dict           # levels, pattern coordinates, p-values, etc.
```

The Signal Fusion component combines `Evidence[]` into a `TradeSignal` carrying the
full list of contributing Evidence objects, the combined probability, and the
threshold comparison that gated execution. This object is what gets persisted and is
the literal payload of the "explainable trade" requirement — not a separate reporting
feature bolted on afterward, but the actual data structure a trade decision is made
of. No trade-decision code path is allowed to produce an `Order` without a
`TradeSignal` behind it.

## 5. Why this satisfies "no shortcuts"

- Every engine boundary above is drawn at a point where the repo analysis showed an
  existing project either got it right (LEAN's model split, NautilusTrader's bus) or
  got it wrong (Backtrader's monolithic single-threaded loop, EA31337's strategy code
  trapped inside the execution venue) — so each boundary is a deliberate, justified
  choice, not a default.
- The dependency rule (kernel depends on nothing else) plus hexagonal ports means MT4
  and MT5 are provably swappable/mockable, which is what makes the Backtesting Engine
  trustworthy: it runs literally the same Strategy/Signal/Risk/Portfolio code, with
  only the Execution Engine and data source swapped.
