# Phased Implementation Roadmap

Each phase is independently shippable and testable — no phase depends on a later
phase's code existing, only on earlier phases' interfaces. This follows directly from
the dependency rule in `02-system-architecture.md`: because `core/` never depends on
`connectors/`, `execution_backends/`, etc., the core can be built and tested (against
mocks/fakes) before any MT4/MT5 code exists at all.

## Phase 0 — Architecture blueprint (this document set)
Deliverable: `docs/architecture/01` through `07`. **Status: done, this session.**
Gate to proceed: user sign-off on the engine boundaries, repo layout, and connector
design before any code is written.

## Phase 1 — Core kernel skeleton
- `core/event_bus`, `core/kernel` (DI container + lifecycle), `core/interfaces`
  (every Protocol from `02-system-architecture.md`), `core/config`, `core/logging`,
  `core/metrics`.
- No engine logic yet — this phase proves the bus/DI/interface skeleton compiles,
  type-checks (strict mypy/pyright), and has unit tests for the bus's pub/sub
  semantics and the DI container's resolution rules (including a CI check enforcing
  the import-direction rule from `03-repo-structure.md`).
- Exit criteria: a fake `Connector` and fake `ExecutionEngine` can be wired through
  the DI container and exchange one round-trip event, fully test-covered.

## Phase 2 — Market Data Engine + Indicator Engine
- Canonical `Tick`/`Bar` types, historical replay source (Parquet-backed) and a fake
  live source (for testing without a real MT connection yet).
- Indicator Engine with a first slice of the Technical Analysis Laboratory (trend +
  momentum categories) to prove the "one indicator implementation, reused everywhere"
  property with actual downstream consumers.
- Exit criteria: identical indicator output whether fed by replay or fake-live source,
  covered by a golden-output regression test.

## Phase 3 — MT5 connector (MT5 before MT4: has an official Python API, so it's the
faster path to a real, working end-to-end system)
- `connectors/mt_common`, `connectors/transport` (ZeroMQ first), `connectors/mt5`.
- Fault tolerance features from `04-mt-connector-design.md` §3 (heartbeat, reconnect,
  reconciliation) built and tested against a real demo MT5 account.
- Exit criteria: live ticks flow from a demo MT5 account into the Market Data Engine;
  a manually-submitted test order round-trips (submit -> fill event -> Position
  Manager reflects it) against the demo account.

## Phase 4 — Order Manager + Execution Engine (backtest + MT5-live)
- `core/execution` (state machine), `execution_backends/backtest` (simplest fill
  model first: spread-only, no latency/partial-fill yet), `execution_backends/live`
  wired to the Phase 3 MT5 connector.
- Exit criteria: the same `Strategy` stub (a trivial always-buy-then-close rule)
  produces consistent, explainable fills in both backtest and MT5 demo live mode.

## Phase 5 — Portfolio Engine + Risk Engine (minimum viable)
- Position Manager, Portfolio Engine CQRS split, and a first Risk Engine slice: kill
  switch, max-position-limit, daily-loss-limit — the non-negotiable safety floor
  before any strategy runs unattended.
- Exit criteria: Risk Engine demonstrably vetoes a signal in an integration test
  (this is the proof that risk sits in the event path, not beside it).

## Phase 6 — Strategy Engine, simple mode
- `init()/next()`-style simple strategy authoring, Plugin Manager strategy
  registration/hot-swap.
- Exit criteria: a real, simple rule-based FX strategy runs unmodified in backtest and
  in MT5 demo-live, producing matching trade counts/timing on the same historical
  window replayed live via a demo tick replay.

## Phase 7 — Signal Engine + first Evidence-producing quant modules
- Signal Fusion skeleton (`quant/fusion`) plus 2–3 real `AnalysisModule`
  implementations (e.g., an ADF-gated mean-reversion module, one Fibonacci
  confluence module, one candlestick module) — enough to prove the Evidence/fusion
  contract end-to-end before building out the full quant library breadth.
- Exit criteria: a `TradeSignal` persists with its full `Evidence[]` trail, queryable
  and human-readable, satisfying the explainability contract from
  `02-system-architecture.md` §4.

## Phase 8 — Backtesting Engine fidelity + Validation Pipeline
- Tick-level simulation, variable spread/commission/swap/slippage models, then the
  full Validation Pipeline gate (`06-backtesting-optimization-risk.md` §4).
- Exit criteria: a strategy cannot reach `mode=live` without a passing Validation
  Report — enforced, not advisory.

## Phase 9 — Optimization Engine
- Grid/Random first (cheapest to validate against Phase 8's out-of-sample
  requirement), then Bayesian/Genetic/PSO, then distributed execution.

## Phase 10 — MT4 connector
- Built against the same `connectors/mt_common` contract proven out by MT5 in Phase 3;
  MQL4 EA as thin forwarder only, per `04-mt-connector-design.md`.

## Phase 11 — Full quant research library breadth
- Fill out remaining Technical Analysis Laboratory categories, Elliott Wave engine,
  harmonic patterns, full SMC/price-action suite, chart pattern recognition —
  each incrementally added as an `AnalysisModule` with no changes to Signal Fusion.

## Phase 12 — Machine Learning Engine + AI assistant layer
- Feature pipeline reuse from `quant/`, calibrated model-as-Evidence integration,
  then the `AIReviewer` assistant layer over the Validation Pipeline.

## Phase 13 — Analytics, Reporting, Notifications at full depth
- Full risk/performance metrics suite, Reporting Engine templates, Notification
  System adapters (email/Slack/Telegram/webhook).

## Phase 14 — Hardening
- Full benchmark suite per engine, chaos-testing the connector fault-tolerance paths
  (kill the MT terminal mid-session, verify reconciliation), load-testing the Event
  Bus, security review, documentation pass.

---

**Immediate next step, pending your go-ahead:** Phase 1 — core kernel skeleton
(`core/event_bus`, `core/kernel`, `core/interfaces`, `core/config`, `core/logging`,
`core/metrics`), with unit tests and the CI import-direction check. This is the
smallest slice that produces real, running, tested code without getting ahead of the
architecture decisions above.
