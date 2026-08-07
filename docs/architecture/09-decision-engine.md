# Phase 8 — Quantitative Signal Fusion / Decision Engine

Scoped and built after an explicit grounding audit against the platform
as it actually exists, rather than against the full nine-output wishlist
in the original brief (confidence, expected return, expected risk,
uncertainty, market regime, probability of success, position size, stop
loss, take profit). Five of those were groundable in existing, tested
code; two needed new infrastructure this pass doesn't build; one
(`market regime`) has no research backing at all. Building the ungrounded
ones anyway would have meant fabricating numbers with no real basis behind
them — exactly what this project's verification discipline exists to
prevent.

## What shipped

| Output | Source |
| --- | --- |
| `confidence` | `TradeSignal.combined_confidence` (`core/signal/fusion.py`), unchanged |
| `probability_of_success` | Same value as `confidence` in this version — see "Known simplification" below |
| `recommended_position_size` | The injected `SizingModel` (`core/interfaces/risk.py`), e.g. `FixedVolumeSizingModel` |
| `recommended_stop_loss` / `recommended_take_profit` | ATR-based (`quant/technical_analysis/volatility.py::compute_atr`), `entry ± atr_multiple·ATR`, take-profit at a configurable risk/reward ratio |
| `uncertainty` | `"low"` / `"medium"` / `"high"`, bucketed by the *weakest* contributing module's historical sample count |

Plus a related, previously-documented-but-unfilled gap closed in the same
pass: `SignalFusion`'s own docstring said *"every module contributes with
equal weight until [historical hit-rate calibration] exists"* — that
calibration engine (`HistoricalHitRateStore`, Phase 13) existed but was
never wired into `SignalFusion` itself. It now optionally is.

## `core/interfaces/reliability.py` — `ModuleReliabilityProvider`

`SignalFusion` lives in `core/`, which must never import `analytics/`
(enforced by `scripts/check_import_direction.py`). `HistoricalHitRateStore`
lives in `analytics/`. The fix is the same pattern already used for
`Connector`/`DataProvider`/`LLMProvider`: a narrow Protocol defined in
`core/interfaces/`, satisfied *structurally* by `HistoricalHitRateStore`
with zero import in either direction (verified:
`isinstance(HistoricalHitRateStore(), ModuleReliabilityProvider)` is `True`
with no code change to the store).

`SignalFusion(threshold=..., reliability_provider=hit_rate_store)` rescales
each Evidence's log-odds contribution by `2 · hit_rate − 1`:

- `hit_rate = 1.0` (module always right) → multiplier `1.0`, full weight, unchanged.
- `hit_rate = 0.5` (no better than a coin flip) → multiplier `0.0`, contribution zeroed.
- `hit_rate = 0.0` (module always wrong) → multiplier `-1.0`, contribution
  **inverted**, not just discarded — a perfectly anti-correlated predictor
  carries exactly as much information as a perfectly correlated one.
- No provider, or not enough samples yet for that module+symbol → multiplier
  `1.0` — the same benefit of the doubt every module had before this
  weighting existed.

Verified empirically (not just asserted) before any test was written: a
"noisy" module with a stronger raw confidence than a "reliable" one flips
the fused signal's direction from what the noisy module wanted to what the
reliable one wanted, once real hit-rate data distinguishes them —
`tests/unit/core/signal/test_fusion.py::test_unreliable_module_no_longer_dominates_a_reliable_one`.

## `decision_engine/` — new top-level package

Placement: outer-layer, alongside `research_lab/`/`news_intelligence/`.
`DecisionEngine` consumes a `TradeSignal` that `SignalFusion` already
produced — it never generates a direction or a signal itself, preserving
"no individual module generates trades independently" exactly.

- `decision_engine/reliability.py` — `HistoricalReliabilityStore`, a
  Protocol requiring both `hit_rate()` and `sample_count()`. Deliberately
  separate from `core.interfaces.reliability.ModuleReliabilityProvider`
  (which only needs `hit_rate()`): each Protocol is minimal to its actual
  consumer, not a shared kitchen-sink interface. Since `decision_engine/`
  is an outer-layer package it *could* import `analytics.hit_rate_store`
  directly, but depending on this narrower Protocol keeps it swappable and
  trivially testable against a fake.
- `decision_engine/report.py` — `DecisionReport`, a frozen dataclass.
- `decision_engine/engine.py` — `DecisionEngine.decide(signal, context, *,
  equity) -> DecisionReport`. Raises `ValueError` if `signal.symbol !=
  context.symbol` rather than silently computing against mismatched
  inputs.

`quant/technical_analysis/volatility.py` gained `compute_true_ranges()`
and `compute_atr()` as reusable functions (previously the ATR math was
inlined only inside `AtrVolatilityBreakoutModule`). The two functions are
*not* interchangeable: `AtrVolatilityBreakoutModule` needs a baseline to
compare the newest bar against, so it excludes the latest true range from
its own average; `compute_atr()` is the conventional trailing average,
inclusive of the latest bar, which is what stop-sizing actually wants.
Both build on the shared `compute_true_ranges()` primitive rather than
duplicating that math — refactored and re-verified behavior-identical
against the existing `AtrVolatilityBreakoutModule` test suite before
either new function was used anywhere else.

## Known simplification: `probability_of_success`

Currently just `combined_confidence` restated. `SignalFusion`'s log-odds
combination already treats each Evidence's confidence as an estimated
probability, so this isn't a fabricated number — but it also isn't yet
independently validated against realized outcomes for *this specific
combination* of contributing modules. A future upgrade path exists and is
intentionally not built yet: extend `HistoricalHitRateStore` (or add a
sibling) to key on the *set* of contributing modules, not just one module
at a time, and substitute that empirical rate once enough combined-signal
history exists — the same "defer to real data once it exists" pattern
already used twice in this platform (`EngulfingPatternModule`'s own
confidence, and this pass's `SignalFusion` weighting).

## Deliberately not built

- **`expected_return` / `expected_risk`.** `HistoricalHitRateStore` only
  tracks win/loss booleans, not return magnitudes, and — more
  fundamentally — nothing in the live pipeline currently feeds realized
  trade outcomes back into any store automatically (no component listens
  for `OrderFilled`/a closed position and calls `record_outcome()`).
  Producing an honest expected-return number needs that feedback loop
  built first, not a plausible-looking number bolted onto `DecisionReport`
  today.
- **A single composite `market_regime` label.** Still not built, and still
  deliberately so: collapsing trend + volatility + everything else into one
  "trending/ranging/crisis"-style tag would overclaim what any of the real
  primitives below actually establish. What *has* since been built (the
  migration plan's Feature Engine and Signal Schema phases) are two
  separate, honestly-computed factual readings on `DecisionReport` — never
  one fabricated composite: `trend_tag` (ADX-confirmed direction/strength,
  `quant/technical_analysis/momentum.py::compute_adx`) and `volatility_tag`
  (this symbol's current volatility percentile against its own recent
  history, `quant/technical_analysis/regime.py::compute_volatility_regime`
  — itself documented as deliberately relative, not an absolute "regime").
  `DecisionReport` also now carries `invalidation_level` (the nearest
  confirmed swing level a trade's structural premise breaks at,
  `quant/price_action/structure.py::compute_structure_invalidation_level`),
  `take_profit_2` (a second, further risk/reward target), and
  `risk_reward_ratio` (echoing the ratio actually used).

## Exit criteria

`tests/integration/test_decision_engine_pipeline.py`: two real quant
`AnalysisModule`s (Fibonacci confluence, Engulfing pattern) feed a
`SignalFusion` weighted by a real `HistoricalHitRateStore`, producing a
`TradeSignal` that flows into a real `DecisionEngine` to produce a full
`DecisionReport` — position size from the injected `SizingModel`,
ATR-based stop-loss/take-profit at the configured risk/reward ratio, and
an uncertainty read correctly gated by the *weakest* contributing module's
sample count (one module has a strong track record, the other has none —
the report is honestly `"high"` uncertainty overall, not averaged away).
