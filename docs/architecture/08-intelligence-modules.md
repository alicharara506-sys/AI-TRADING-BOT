# Intelligence Modules — Architectural Placement

Follow-up to the Phase 1/2 research pass over four external repositories
(`opennews-mcp`, `nof1-tracker`, `ai-trading-agent-gemini`,
`Awesome-Prediction-Market-Trading-Tools`). This document is the Phase 7
deliverable: where each new capability lives, and why, before any of it is
built. The rule carried over from every earlier phase applies unchanged:
`core/` never imports outward, enforced by
`scripts/check_import_direction.py`.

## Placement decisions

| Capability | Package | New or extend? | Status |
| --- | --- | --- | --- |
| Experiment Management | `research_lab/` | New, top-level | Delivered. `ExperimentLog`, `significance.py`, adapters for `OptimizationTrial`/`ValidationReport`, `reporting.py`. |
| AI Intelligence | `machine_learning/ai_assistant/` | Extend | Delivered. `LLMProvider` Protocol, `ConfidenceScoredOpinion` schema, `LLMBackedReviewer` (fallback-composing). `AIReviewer` is now async. |
| News Intelligence | `news_intelligence/` | New, top-level | Delivered. `NewsProvider` Protocol, dedup/classification/language/sentiment/entity/scoring pipeline, `NewsSentimentModule` (AnalysisModule). |
| Prediction Intelligence | *(none yet)* | Deferred | The only named research source turned out to be illegitimate (see the Phase 1 report — a repurposed exploit/bot repo with affiliate-link marketing, zero usable content). No package is created until a real research pass exists to inform the design. |

Reasoning for each placement: `research_lab/` sits at the same layer as
`optimization/`/`backtesting/` — it observes and records their outputs,
never the reverse. `machine_learning/ai_assistant/` already owned the
`AIReviewer`/`RuleBasedReviewer` namespace since Phase 12, so a new
`LLMProvider` Protocol and a fallback-composing reviewer are natural
additions to an existing interface-isolated boundary, not a new domain.
`news_intelligence/` is a genuinely new domain with no existing home; it
needs its own `NewsProvider` Protocol so specific vendors are adapters,
not the interface.

## Dependency direction

All three active new packages (`research_lab/`, the `machine_learning/`
extension, `news_intelligence/`) are outer-layer packages exactly like
`optimization/`, `backtesting/`, `analytics/`, `reporting/`: they may import
from `core/`, but `core/` must never import from them. `research_lab/` and
`news_intelligence/` are added to the `FORBIDDEN_FROM_CORE` set in
`scripts/check_import_direction.py` alongside the existing outer packages,
and both are registered in `pyproject.toml` (`mypy` packages, setuptools
`include`) and the CI `mypy` command, following the exact pattern every
prior phase used.

## How each plugs into Signal Fusion

No changes to `core/signal/fusion.py` or `core/signal/engine.py` are
needed. `NewsSentimentModule` (`news_intelligence/signal_module.py`)
implements `analyze(context: MarketContext) -> list[Evidence]` and
registers with `SignalEngine.register_module()` exactly like
`EngulfingPatternModule` or `MLPredictionModule` already do. This was true
before this research pass and remains true after it — it's the reason the
hexagonal design from Phase 0 was chosen — and it's no longer a claim:
`tests/integration/test_news_intelligence_engine.py` proves it against a
real `SignalEngine`/`SignalFusion` composed with the existing Fibonacci
and Engulfing modules plus `NewsSentimentModule`, unmodified.

AI-derived text (from `LLMBackedReviewer`) does not currently feed
Evidence directly — `AIReviewer`'s contract is prose explanation, not a
directional signal. A future `AIOpinionModule` translating a
`ConfidenceScoredOpinion` into `Evidence` would follow the identical
pattern once there's a concrete need for it; it isn't built speculatively
here.

## What was deliberately not built in this pass

- **Concrete LLM vendor integrations** (Claude/OpenAI/Gemini/DeepSeek).
  `LLMProvider` and the fallback wiring are real and tested against a fake
  provider; a concrete implementation needs live credentials to verify
  against, which this environment doesn't have. Same relationship
  `MT5Connector` has to the real `MetaTrader5` package.
- **Concrete news vendor integrations** (Reuters, Bloomberg, Financial
  Modeling Prep, Alpha Vantage, NewsAPI, Polygon, Finnhub). `NewsProvider`
  and the full analysis pipeline are real and tested against a fake
  provider; wiring a specific vendor's REST API is a follow-up that plugs
  into the same tested contract.
- **Topic modeling in the LDA/clustering sense.** The engine's "topic" is
  the deterministic category taxonomy (`NewsCategory`) plus extracted
  entities, not a trained topic model — there's no real corpus in this
  environment to train or validate one against, and claiming otherwise
  would be exactly the kind of unverifiable capability this project's
  discipline avoids.
- **Prediction Intelligence entirely** (see the placement table above).

## What `research_lab/` actually is

An append-only, replayable log of research experiments — backtests,
optimization trials, validation runs — keyed by a composite hash of
`(kind, subject_name, parameters)` so re-running an identical trial is
idempotent rather than double-recorded. This pattern is directly evidenced
by `nof1-tracker`'s `OrderHistoryManager` (state reconstructed by replaying
an append-only log rather than trusted in-memory state) and its
composite-key dedup guard — translated from "don't double-execute an
order" to "don't double-count a trial." It wraps the existing
`OptimizationTrial`/`OptimizationResult` (Phase 9) and `ValidationReport`
(Phase 8) types rather than replacing them; those types already have the
right shape, they just weren't durably logged across runs before now.
