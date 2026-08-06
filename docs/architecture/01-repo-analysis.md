# Reference Repository Analysis

Purpose: extract what's worth stealing and what to avoid, from each reference project,
specifically through the lens of an MT4/MT5-only institutional platform. None of these
architectures are adopted wholesale — this is a teardown, not a merge.

---

## NautilusTrader

**Strongest ideas to take:**
- **Single codebase, backtest == live.** Strategies are written once against an
  abstract `Strategy`/`Actor` interface; the same code runs against a simulated
  `ExecutionEngine` in backtest and a real one in production. This is the single most
  important property we want to copy — it eliminates the "backtest lied to me"
  failure mode that kills most retail systems.
- **Message bus / event-driven core.** Every component (data engine, execution engine,
  risk engine, strategies) talks only through an internal message bus with typed
  events (`TradeTick`, `OrderFilled`, `PositionChanged`, etc). No direct method calls
  between engines. We adopt this as our **Event Bus** pattern.
- **Nanosecond-precision, deterministic clock abstraction.** A `Clock` interface that
  is swappable between `LiveClock` and `TestClock` so backtests are fully
  deterministic and replayable.
- **Adapters as isolated plugins.** Venue integrations are adapters implementing a
  fixed interface, isolated from the core engine. This is exactly the shape we want
  for the MT4/MT5 connector — the core must never import anything MT-specific.

**Weaknesses / what we discard:**
- Rust core + Cython/Python bindings is a major build/deploy/tooling burden for a
  team that isn't going to maintain a Rust runtime. We take the *architecture*, not
  the *implementation language*. We'll get equivalent hot-path performance with
  Numba/vectorization/asyncio rather than a Rust rewrite, at far lower maintenance
  cost for a small team.
- Broad multi-venue adapter surface (crypto exchanges, equities venues) is dead
  weight for an MT4/MT5-only platform — none of that gets ported.

---

## QuantConnect LEAN

**Strongest ideas to take:**
- **Algorithm Framework separation:** Alpha Model (signal generation) / Portfolio
  Construction Model / Execution Model / Risk Management Model as **independently
  swappable, composable interfaces**, orchestrated by a coordinator. This maps almost
  exactly onto our required Signal Engine / Portfolio Engine / Execution Engine /
  Risk Engine split, and is the cleanest existing precedent for "strategies are
  composition of independent models" rather than monolithic strategy classes.
- **Brokerage abstraction layer** — a clean `IBrokerage` interface with symbol
  mapping, order translation, and reconciliation, independent of the algorithm code.
  Directly informs our MT4/MT5 connector interface contract.
- **Universe selection / data subscription model** — declarative "what symbols and
  what resolutions does this strategy need," resolved by the engine rather than
  hardcoded per-strategy. Useful for our multi-symbol/multi-timeframe strategy
  requirement.

**Weaknesses / what we discard:**
- Deep coupling to a hosted cloud product (QuantConnect Cloud) and a C#/.NET-first
  engine with Python running through a lightweight wrapper — heavier runtime than we
  need for an MT-only, self-hosted system.
- Its brokerage integrations are all traditional/equities/crypto brokers; nothing
  MT4/MT5-specific to reuse directly.

---

## StockSharp (S#)

**Strongest ideas to take:**
- **Connector abstraction with 200+ implementations** proves the value of a strict,
  narrow connector interface (`IConnector`: `Connect`, `RegisterOrder`,
  `RegisterMarketData`, event callbacks for ticks/order changes/positions). Even
  though we only need one connector family (MT4 + MT5), we adopt the discipline of
  designing that interface as if it had to support 200 venues — it forces the
  interface to be minimal and venue-agnostic, which prevents MT4/MT5-specific leakage
  into the core engine.
- **Designer** (visual strategy composition) and **Hydra** (dedicated market-data
  collector service, decoupled from the trading engine) are useful separation-of-
  concerns precedents: market data collection/storage is its own service, not bolted
  onto the strategy runtime. We adopt a standalone **Market Data Engine** service for
  the same reason.

**Weaknesses / what we discard:**
- .NET/C#-centric tooling (Designer, Hydra as WPF apps) — we're not shipping desktop
  GUI apps as core infrastructure.
- License ambiguity/dual-licensing model for parts of the suite — irrelevant to
  extract-and-redesign, but a reminder to keep our own licensing decision explicit
  (see the closing note in the previous reference doc).

---

## Backtrader

**Strongest ideas to take:**
- **`Lines` abstraction** — indicators, data feeds, and strategies all operate over a
  uniform time-series buffer object with lookback indexing (`self.data.close[-1]`).
  This is a genuinely good ergonomic pattern for an Indicator Engine: one uniform
  buffer type consumed identically by indicators, strategies, and analyzers, whether
  in backtest or live.
- **Analyzers as pluggable, composable result extractors** attached to a strategy run
  (Sharpe, drawdown, SQN, etc. as separate analyzer objects rather than baked into the
  engine). Directly informs our Analytics Engine as a plugin-based, not hardcoded,
  system.

**Weaknesses / what we discard:**
- Project is effectively unmaintained (high star count, but development has been
  dormant for years) — a warning sign, not a pattern: it shows what happens when an
  otherwise-good architecture has no institutional backing. We take the `Lines`/
  analyzer *patterns*, not the codebase or its dependency choices (single-threaded
  `cerebro` event loop is a bottleneck we explicitly design around with our
  async/multiprocess Backtesting Engine).
- Live broker support (IB, Oanda, Visual Chart) is bolted on and not first-class —
  confirms our decision to make execution a first-class engine from day one rather
  than an afterthought.

---

## backtesting.py

**Strongest ideas to take:**
- **Radical API minimalism.** A strategy is `init()` + `next()`, full stop. This is
  the right *default* ergonomic for the simplest class of rule-based strategies in
  our Strategy Framework — not every strategy needs the full Alpha/Portfolio/
  Execution/Risk model composition from LEAN; a lightweight path should exist for
  simple cases, layered on top of the same kernel.
- **Built-in vectorized-first optimizer** with a simple grid/random search interface
  — a good minimum bar for our Optimization Engine's simplest strategy (Grid Search)
  before layering Bayesian/genetic/PSO on top.

**Weaknesses / what we discard:**
- Backtest-only, no live path at all, and no multi-asset/portfolio concept (single
  `Strategy` over a single OHLC series) — far too narrow for an institutional
  platform; we only take the API-ergonomics lesson, not the architecture.
- AGPL-3.0 licensing is a concrete reason not to import or link any of its code
  directly — anything inspired by it must be an independent reimplementation.

---

## EA31337

**Strongest ideas to take:**
- **It's the only reference project actually built for MT4/MT5**, so its strategy
  library is the most direct source of concrete FX trading logic and MT-specific risk
  patterns (spread/slippage handling, per-symbol parameter sets, hedging-aware
  position management) — valuable as domain reference for our Risk Engine and
  Strategy Framework defaults, even though we don't reuse any MQL code.
- **Per-strategy parameter sets keyed by symbol/timeframe** is a pattern worth
  keeping: risk and entry parameters are not global constants but resolved per
  (symbol, timeframe, strategy) tuple — matches our multi-symbol/multi-timeframe
  strategy requirement.

**Weaknesses / what we discard:**
- MQL4/MQL5 as the implementation language is precisely the limitation we're
  removing: single-threaded, no real backtosting-engine independence from the
  MetaTrader Strategy Tester (which has well-known tick-simulation inaccuracies),
  no first-class Python/ML integration. Our platform treats MT4/MT5 purely as an
  **execution venue**, driven from outside via our connector — no strategy logic ever
  runs inside MQL.

---

## exchange-api (fawazahmed0)

**Strongest ideas to take:**
- Simple, cacheable, versioned static-JSON API design (date-partitioned endpoints,
  CDN-fronted) is a reasonable pattern for our own **reference/conversion rate cache**
  (e.g., for cross-rate normalization, margin currency conversion) — cheap to
  replicate internally rather than depend on.

**Weaknesses / what we discard:**
- Daily granularity, currency-conversion-only — not a market data source for trading
  decisions. We do not build any execution or signal logic on top of this; at most it
  informs a low-priority utility module for currency normalization in reporting.

---

## QuantDinger

**Strongest ideas to take:**
- **End-to-end shape**: strategy idea -> Python strategy -> backtest -> paper trade ->
  live -> monitoring, as one coherent local-first stack, is the closest existing
  precedent to the *product shape* we're building (minus the MT4/MT5 focus and minus
  the crypto/multi-broker breadth).
  Confirms our engine boundaries (Strategy Engine -> Backtesting Engine -> Paper/Live
  Execution Engine -> Analytics/Reporting) should be the same code path end-to-end,
  differing only in which Execution Engine implementation is wired in (simulated vs.
  MT4/MT5-backed).
- Multi-provider AI integration as a layer that assists strategy development rather
  than replacing human-authored strategies — matches our AI subsystem's intended role
  (reviewer/optimizer/explainer, not an autonomous black box).

**Weaknesses / what we discard:**
- Crypto-exchange-first with traditional brokers as secondary — inverse of our
  priority. We take none of its broker/exchange integration code; MT4/MT5 is the only
  execution venue in our system.

---

## Cross-cutting conclusions

1. **The Alpha/Portfolio/Execution/Risk model split (LEAN) + message-bus event-driven
   core (NautilusTrader) is our architectural spine.** Every other pattern below
   attaches to that spine.
2. **Uniform time-series buffer (Backtrader's `Lines`)** becomes our Indicator Engine's
   core data type, used identically in backtest and live.
3. **Narrow, venue-agnostic connector interface (StockSharp)** is the contract our
   MT4/MT5 connector implements — designed as if more venues could be added later,
   even though none will be.
4. **Pluggable analyzers (Backtrader) + declarative universe/data subscription
   (LEAN)** shape our Analytics Engine and Market Data Engine respectively.
5. **Simple `init()/next()` ergonomic (backtesting.py)** is preserved as an on-ramp
   for simple strategies, sitting on top of the same kernel full institutional
   strategies use — we do not force every strategy author through the full
   Alpha/Portfolio/Risk composition if they don't need it.
6. **No project here treats MT4/MT5 as a first-class, high-fidelity execution
   venue with a robust reconnecting connector** — this is the actual gap our
   platform fills; EA31337 is MT-native but throws away everything else (no real
   backtesting engine, no ML, no risk engine, no portfolio concept). That gap is the
   platform's reason to exist.
