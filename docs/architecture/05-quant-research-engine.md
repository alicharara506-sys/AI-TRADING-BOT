# Quantitative Research & Signal Fusion Engine

This is the `quant/` package tree from `03-repo-structure.md`, expanded. It implements
every analytical discipline in the spec as an independent plugin producing `Evidence`
(defined in `02-system-architecture.md` §4), fused into `TradeSignal` by a single
probabilistic decision engine. **No individual module ever emits a trade decision.**

## 1. Design principle: layers are independent, fusion is centralized

Every module below implements one interface:

```
AnalysisModule(Protocol):
    name: str
    analyze(context: MarketContext) -> list[Evidence]
```

`MarketContext` bundles the canonical Bar/Tick buffers (from the Indicator Engine),
current positions/exposure (read-only Portfolio query), and any auxiliary data
(news events, economic calendar). Modules are pure functions of this context — no
module holds hidden state that isn't reconstructable from `MarketContext`, which is
what makes backtest and live produce identical Evidence given identical history.

This means: adding a new analytical discipline never touches Signal Fusion, and
Signal Fusion never needs to know how a p-value or a wave count was produced — only
the `Evidence.confidence` and `Evidence.direction` it emits.

## 2. Mathematical & statistical layer (`quant/math_models`, `quant/statistics`)

- **Linear algebra / spectral**: PCA/SVD for cross-symbol factor decomposition,
  eigenvalue-based regime detection, FFT/wavelet/Hilbert transform for cycle and
  dominant-frequency extraction, implemented once as shared utilities (NumPy/SciPy),
  consumed by both statistics and technical-analysis modules rather than
  reimplemented per-module.
- **Filtering / state-space**: Kalman filter and HMM implementations used for
  trend/regime state estimation (e.g., a Kalman-filtered trend estimate is itself an
  `AnalysisModule` emitting directional Evidence with confidence tied to filter
  residual variance).
- **Statistical test battery** (`quant/statistics/tests.py`): ADF, KPSS, Ljung-Box,
  Durbin-Watson, Granger causality, cointegration tests — used primarily for
  **regime/stationarity gating**: e.g., a mean-reversion strategy's Evidence carries
  near-zero confidence when an ADF test fails to reject a unit root on the relevant
  window. This is how "no strategy relies on a single indicator" is enforced
  structurally — directional indicators are gated by the statistical layer, not just
  combined with equal weight.
- **Risk/performance statistics** (Sharpe, Sortino, Calmar, Omega, VaR/CVaR, Kelly,
  SQN, etc.) live in `analytics/` (not `quant/`) since they characterize a strategy's
  historical performance, not a single market observation — consumed by the
  Backtesting/Optimization engines and by the Risk Engine's position-sizing models
  (Kelly, volatility sizing), not by Signal Fusion directly.

## 3. Technical Analysis Laboratory (`quant/technical_analysis`)

Organized by category (trend, momentum, volume, volatility) exactly as in the spec,
each indicator implemented once against the canonical Bar buffer (Indicator Engine)
and wrapped by a thin `AnalysisModule` adapter that converts an indicator's numeric
output into directional `Evidence` with a confidence derived from e.g. distance from a
threshold, slope, or historical hit-rate for that indicator/symbol/timeframe
combination (looked up from the Analytics Engine's historical performance store —
confidence is empirical, not a fixed constant per indicator).

## 4. Price Action Engine (`quant/price_action`)

Automatic market-structure detection: swing highs/lows, trendlines, channels,
consolidation/expansion/compression regimes, Wyckoff phase heuristics. Smart Money
Concepts (order blocks, breaker/mitigation blocks, fair value gaps, premium/discount
zones, BOS/CHOCH, liquidity sweeps, Optimal Trade Entry) are implemented as a
sub-module of this engine since they're defined in terms of the same swing/structure
primitives — avoiding duplicate swing-detection logic between "price action" and "SMC"
as separate systems (a duplication the repo analysis flagged as a general anti-pattern
to eliminate).

## 5. Fibonacci Engine (`quant/fibonacci`)

- **Automatic swing detection** feeds retracement/extension/expansion/projection
  calculations — never manually drawn.
  Shares the swing-detection primitive from §4 (single implementation, not
  reimplemented per-engine).
- **Time zones, fans, arcs** computed from the same detected swings.
- **Cluster/confluence detection**: overlays retracement levels from multiple swings
  and multiple timeframes; a level gets higher `Evidence.confidence` the more
  independent Fibonacci calculations converge on it within a configurable tolerance
  band — this is the "automatically identify the most statistically relevant levels"
  requirement, implemented as a density/clustering computation over generated levels,
  not a heuristic pick.
- **Multi-timeframe Fibonacci heat map**: a derived visualization/analytics artifact
  built from the same confluence data, exposed to Reporting, not a separate
  calculation path.

## 6. Elliott Wave Engine (`quant/elliott_wave`)

- Automatic wave counting over the swing/structure primitives from §4, validated
  against hard Elliott rules (wave 2 never retraces beyond wave 1 start, wave 3 never
  shortest, wave 4 doesn't overlap wave 1 in impulses, etc.) as a rule-checker that
  **rejects** invalid counts rather than a generator that assumes correctness.
- **Multiple simultaneous hypotheses**: the engine maintains a ranked list of valid
  wave counts (impulse/corrective/zigzag/flat/triangle/complex), each scored by rule
  compliance + Fibonacci-ratio confluence (reusing §5) + multi-timeframe alignment.
  Only the top-ranked hypothesis (or hypotheses above a confidence floor) contribute
  `Evidence`; the full ranked list is retained in `Evidence.supporting_data` for
  explainability — never collapsed to a single silent "the" count.

## 7. Harmonic Pattern Engine (`quant/harmonics`)

Detects Gartley/Butterfly/Bat/Crab/Deep Crab/Shark/Cypher/Three Drives/ABCD/Alternate
Bat via XABCD point detection over the same swing primitive (§4) plus Fibonacci ratio
matching (§5). Each detected pattern is scored on ratio-symmetry error and, critically,
**looked up against the Analytics Engine's historical outcome store** for that pattern
type/symbol/timeframe — the "historical performance" scoring requirement is real
backtested statistics per pattern instance, not a static textbook weight.

## 8. Candlestick & Chart Pattern Recognition (`quant/candlesticks`, `quant/chart_patterns`)

- Candlestick patterns detected via geometric rules over OHLC (body/wick ratios,
  multi-bar sequences), each pattern's `Evidence.confidence` derived from a rolling
  historical win-rate for that exact pattern/symbol/timeframe from the Analytics
  Engine — not a fixed textbook reliability figure.
- Chart patterns (H&S, double/triple top/bottom, triangles, wedges, flags, pennants,
  cup & handle, broadening, diamond) detected via structural/geometric matching over
  the swing primitive (§4), each emitting target/stop/historical-win-rate/confidence
  as required — target/stop derived from the pattern's own geometry (e.g. H&S
  head-to-neckline projection), historical win-rate from the same Analytics lookup
  used by harmonics and candlesticks, so all pattern families share one
  "look up empirical performance" code path rather than three separate ones.

## 9. Machine Learning layer (`machine_learning/`)

ML models (classification/regression/RL/ensemble) are `AnalysisModule` implementations
like everything else — a trained model's prediction becomes `Evidence` with confidence
derived from the model's own calibrated probability output (models are required to be
probability-calibrated, e.g. via Platt scaling/isotonic regression, precisely so their
confidence is comparable to every other module's confidence in the fusion step).
Feature extraction reuses the Indicator Engine and other `quant/` modules' outputs as
features rather than recomputing raw features independently — one feature pipeline
shared between classical and ML analysis.

## 10. Signal Fusion (`quant/fusion`)

- Collects `Evidence[]` from every registered `AnalysisModule` for the current
  `MarketContext`.
- Computes a combined directional probability via a configurable combination rule
  (default: confidence-weighted Bayesian combination treating each module's Evidence
  as a conditionally-independent likelihood update — not naive averaging, since equal
  weighting would let ten weak/correlated indicators outvote one strong statistical
  test). Weights per module are themselves calibrated from the Analytics Engine's
  historical hit-rate of that module, and are periodically recalibrated, not
  hand-tuned constants.
- Emits `TradeSignal` only when combined probability crosses a configurable
  institutional threshold (per-strategy, per-symbol configurable via the
  Configuration System) — below threshold, Evidence is still logged (for research/ML
  training) but no `TradeSignal` is produced.
- `TradeSignal` carries the complete `Evidence[]` list, the combination weights used,
  and the threshold comparison — this **is** the explainability requirement: nothing
  extra needs to be built to "explain" a trade, because the trade's causal record is
  its own data structure, persisted by the Database Layer alongside the resulting
  order and P&L for later audit.

## 11. Validation feedback loop

The Analytics Engine's historical hit-rate store (used above for indicator/pattern/ML
confidence calibration) is itself fed by the Backtesting/Validation pipeline in
`06-backtesting-optimization-risk.md` — closing the loop: strategy validation results
feed back into how much the fusion engine trusts each Evidence source going forward,
rather than confidence weights being static.
