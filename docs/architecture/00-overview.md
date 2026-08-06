# Architecture Blueprint — Index

This directory is the Phase 0 deliverable: a from-first-principles architecture for an
institutional-grade, MT4/MT5-only quantitative trading platform, designed by tearing
down eight reference open-source projects for ideas and anti-patterns, not by merging
or forking any of them.

Read in order:

1. [`01-repo-analysis.md`](./01-repo-analysis.md) — what's worth taking and what's
   discarded from NautilusTrader, QuantConnect LEAN, StockSharp, Backtrader,
   backtesting.py, EA31337, exchange-api, and QuantDinger.
2. [`02-system-architecture.md`](./02-system-architecture.md) — the unified engine
   architecture: Event Bus, Trading Kernel engines, dependency rules, and the
   Evidence/explainability contract.
3. [`03-repo-structure.md`](./03-repo-structure.md) — the monorepo layout and the CI
   rules that enforce the dependency rules from (2).
4. [`04-mt-connector-design.md`](./04-mt-connector-design.md) — the MT4/MT5
   connector: interface contract, transports, fault tolerance, account/margin/news
   integration.
5. [`05-quant-research-engine.md`](./05-quant-research-engine.md) — the full
   multi-layer quantitative analysis engine (math, statistics, technical analysis,
   price action/SMC, Fibonacci, Elliott Wave, harmonics, patterns, ML) and the
   Signal Fusion decision engine.
6. [`06-backtesting-optimization-risk.md`](./06-backtesting-optimization-risk.md) —
   the Backtesting Engine, Optimization Engine, Risk Engine, and the mandatory
   Strategy Validation Pipeline.
7. [`07-roadmap.md`](./07-roadmap.md) — the phased build-out, each phase independently
   shippable and testable, with concrete exit criteria per phase.

## Status

Phase 0 (this document set) is complete. No implementation code has been written yet
— per the roadmap's own process, code begins at Phase 1 (core kernel skeleton) only
after this blueprint is reviewed and confirmed.
