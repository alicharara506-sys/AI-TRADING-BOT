# Intelligence Modules — Architectural Placement

Follow-up to the Phase 1/2 research pass over four external repositories
(`opennews-mcp`, `nof1-tracker`, `ai-trading-agent-gemini`,
`Awesome-Prediction-Market-Trading-Tools`). This document is the Phase 7
deliverable: where each new capability lives, and why, before any of it is
built. The rule carried over from every earlier phase applies unchanged:
`core/` never imports outward, enforced by
`scripts/check_import_direction.py`.

## Placement decisions

| Capability | Package | New or extend? | Reasoning |
| --- | --- | --- | --- |
| Experiment Management | `research_lab/` | New, top-level | No existing package owns "durable record of a research run." Sits at the same layer as `optimization/`/`backtesting/` — it observes and records their outputs, never the reverse. |
| AI Intelligence | `machine_learning/ai_assistant/` | Extend | Phase 12 already established this namespace (`AIReviewer` Protocol, `RuleBasedReviewer`). A new `LLMProvider` Protocol and a fallback-composing reviewer are natural additions to an existing interface-isolated boundary, not a new domain. |
| News Intelligence | `news_intelligence/` | New, top-level | Genuinely new domain with no existing home; needs its own `NewsProvider` Protocol so specific vendors (or the current placeholder) are adapters, not the interface. |
| Prediction Intelligence | *(none yet)* | Deferred | The only named research source turned out to be illegitimate (see the Phase 1 report — a repurposed exploit/bot repo with affiliate-link marketing, zero usable content). No package is created until a real research pass exists to inform the design. |

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
needed. Any future news-derived or AI-derived signal is just another
`AnalysisModule`: it implements `analyze(context: MarketContext) ->
list[Evidence]` and registers with `SignalEngine.register_module()` exactly
like `EngulfingPatternModule` or `MLPredictionModule` already do. This was
true before this research pass and remains true after it — it's the reason
the hexagonal design from Phase 0 was chosen, and this pass is the first
real test of whether that promise holds under a capability nobody had
designed for yet. It holds.

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
