# Backtesting, Optimization, Risk & Validation Engines

## 1. Backtesting Engine (`backtesting/engine`)

**Core guarantee**: the Backtesting Engine runs the exact same Strategy Engine,
Signal Engine, Portfolio Engine, and Risk Engine code as live trading (per
`02-system-architecture.md` §2.8). The only substitutions are:
- `MarketDataEngine` source: historical tick/bar replay instead of live connector feed.
- `ExecutionEngine`: `BacktestExecutionEngine` (simulated fills) instead of
  `MT4ExecutionEngine`/`MT5ExecutionEngine`.
- `Clock`: `TestClock` (deterministic, driven by data timestamps) instead of
  `LiveClock`.

Everything else — including the Risk Engine sitting in the event path and vetoing
signals — runs unmodified. This is what makes "backtesting accuracy should closely
match real MT4/MT5 execution" achievable: there is no separate backtest-only strategy
code path to drift out of sync with live.

### Simulation fidelity
- **Tick-level simulation** (primary, most accurate): replays actual tick sequences;
  OHLC bars are derived from ticks, not the reverse.
- **OHLC-only simulation** (fallback when tick history is unavailable): uses a
  configurable intra-bar fill model (worst-case, optimistic, or Monte Carlo-sampled
  intra-bar path) — always explicitly labeled as lower-fidelity in results output, so
  users can't accidentally treat OHLC-simulated results as tick-accurate.
- **Variable spread model**: spread sampled from historical spread distribution per
  symbol/session (Asian/London/NY) rather than a fixed constant.
- **Commission, swap (including triple-swap Wednesday), and slippage models**:
  pluggable, symbol/broker-configurable, registered through the Plugin Manager like
  any other extension point.
- **Latency simulation**: configurable order-to-fill delay distribution, so
  strategies sensitive to execution latency (e.g., scalping) get realistic
  degradation in backtest rather than instant fills.
- **Order queue / partial fill simulation**: pending orders fill against simulated
  book depth/volume rather than assuming full fill at touch price.
- **Multi-threaded execution**: independent backtest runs (e.g., one per
  symbol/parameter-set in an optimization sweep) are embarrassingly parallel and run
  across processes; a single run's event replay is single-threaded and deterministic
  (determinism required for reproducibility — never parallelize *within* one
  strategy's event stream).

## 2. Optimization Engine (`optimization/`)

- Common `Optimizer` interface: given a parameter space, an objective function
  (any Analytics Engine metric — Sharpe, Sortino, Calmar, custom composite), and a
  backtest run function, produce ranked parameter sets.
- Algorithms, from simplest to most capable (matching the backtesting.py-to-genetic
  spectrum from the repo analysis, so a strategy author can start with Grid Search and
  graduate to genetic/Bayesian without changing anything else):
  Grid Search, Random Search, Bayesian Optimization, Genetic Algorithms, Particle
  Swarm Optimization, Multi-objective optimization (Pareto front over e.g. return vs.
  max drawdown), Distributed/parallel optimization (same run function, fanned out
  across worker processes/machines).
- **Overfitting guard is structural, not optional**: every optimizer run requires an
  out-of-sample evaluation window and reports in-sample vs. out-of-sample metric
  degradation alongside the optimized parameters — an optimization result without an
  out-of-sample comparison is not a valid output of this engine.

## 3. Risk Engine (`core/risk`)

Already positioned architecturally in `02-system-architecture.md` §2.6 (in the event
path, not beside it). Concrete responsibilities:

- **Position sizing models** (pluggable): Kelly Criterion, ATR-based, volatility-based
  — selected per-strategy via config, implemented against a common `SizingModel`
  interface so new sizing logic doesn't touch the Risk Engine core.
- **Portfolio-level controls**: symbol exposure limits, portfolio exposure limits,
  correlation-aware exposure (won't stack correlated positions past a configured
  correlation threshold — uses the correlation analysis from the statistics layer).
- **Loss/drawdown controls**: daily loss limit, max drawdown limit, max concurrent
  positions — each independently configurable, each capable of triggering the kill
  switch.
- **Kill switch**: a single, testable, always-on subscriber to account/position state
  that can halt all new order submission platform-wide (not per-strategy) — the one
  component every other engine's failure mode should degrade toward.
- **Execution-quality guards**: slippage monitoring (compares expected vs. actual fill
  price, feeds back into the Analytics Engine), spread protection (refuses entries
  when spread exceeds a configured multiple of normal), liquidity filters (session-
  aware, e.g. avoiding thin-liquidity rollover windows), and trade throttling
  (rate-limiting order submission per symbol/strategy to avoid runaway loops).
- **Margin protection**: continuously evaluates margin level from `AccountState`
  (connector-sourced, per `04-mt-connector-design.md` §4) against configured minimum
  margin-level thresholds, pre-emptively blocking new orders before a margin call, not
  reactively after one.

## 4. Strategy Validation Pipeline (`backtesting/validation`)

A strategy is not eligible for live deployment until it passes this pipeline, which is
a required gate, not an optional analysis:

- **Walk-forward analysis**: rolling optimize-in-sample / test-out-of-sample windows;
  reports parameter stability across windows (a strategy whose optimal parameters
  swing wildly window-to-window fails this gate even with good average returns).
- **Monte Carlo simulation**: reshuffles trade sequence/returns to build a
  distribution of possible equity curves, reporting drawdown/ruin probability rather
  than a single historical path.
- **Bootstrap resampling** and **cross-validation**: statistical confidence on
  performance metrics, not just point estimates.
- **Regime testing / stress testing**: evaluates the strategy specifically across
  known distinct volatility/trend regimes (segmented via the same regime-detection
  tools from `05-quant-research-engine.md` §2), and against synthetic stress
  scenarios (gap events, spread spikes, liquidity gaps).
- **Sensitivity analysis / parameter stability**: perturbs each parameter
  independently and measures performance-metric sensitivity — flags fragile,
  narrow-optimum parameter choices.
- **Overfitting detection**: in-sample vs out-of-sample degradation (from the
  Optimization Engine's structural requirement, §2), plus a check on the ratio of
  parameters to number of independent trades (too many degrees of freedom relative to
  sample size fails this gate automatically).
- **Survivorship bias / look-ahead bias detection**: static checks over the
  backtest's data pipeline (e.g., confirms delisted/inactive symbols are included
  where relevant, confirms no feature/indicator at bar N reads data timestamped after
  bar N) — implemented as automated pipeline assertions, not a manual review
  checklist.

Only a strategy that clears every gate above produces a **Validation Report**, and
only a strategy with a passing Validation Report can be attached to a live
`MT4ExecutionEngine`/`MT5ExecutionEngine` — enforced by the Strategy Engine's
deployment path checking for a valid, non-expired Validation Report before allowing
`mode=live` activation.

## 5. AI subsystem's role in this pipeline (`machine_learning/ai_assistant`)

Positioned as a reviewer/assistant over the above pipeline, per the repo analysis'
QuantDinger-derived conclusion that AI should assist rather than autonomously decide:
- Reviews Validation Report output and flags likely overfitting or fragile parameter
  regions in natural language, backed by the same numeric evidence the pipeline
  already produced (not an independent, opaque judgment).
- Generates strategy documentation and plain-language explanations of a
  `TradeSignal`'s `Evidence[]` trail (from `05-quant-research-engine.md` §10) for
  human review.
- Suggests parameter/optimization search-space adjustments to the Optimization Engine
  — a suggestion the user/optimizer accepts or rejects, never an auto-applied change
  to a live strategy's parameters.
- Interface-isolated (`AIReviewer` Protocol) specifically so a future/different LLM
  provider is a swap-in, per the spec's "design this layer so future LLMs can
  integrate with minimal changes" requirement.
