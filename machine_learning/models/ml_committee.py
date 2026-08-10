from __future__ import annotations

import contextlib
from collections.abc import Sequence

from core.interfaces.types import Bar, Direction, Evidence, MarketContext
from machine_learning.features.expanded_extractor import ExpandedFeatureExtractor
from machine_learning.labeling.triple_barrier import build_training_labels
from machine_learning.models.pattern_matcher import PatternMatcher
from machine_learning.models.rule_forest import RuleForest

DEFAULT_COMMITTEE_WEIGHT = 0.15


class MLCommittee:
    """Combines RuleForest and PatternMatcher -- two structurally different
    lightweight models (indicator-threshold-split ensemble vs. raw
    price-shape k-NN) -- into a single AnalysisModule vote, so the ML layer
    plugs into the existing SignalFusion pipeline exactly like every quant
    module already does, contributing its own Evidence rather than running
    as a parallel, separately-weighted system.

    `weight` (default 0.15) scales the committee's combined confidence down
    before it becomes Evidence, expressing "15% ML committee, 85% existing
    factor modules" as a confidence multiplier: SignalFusion has no notion
    of a fixed percentage weight per factor (Evidence is combined via
    log-odds summation, see core/signal/fusion.py), so scaling this one
    module's own confidence is how that intent is expressed inside this
    platform's actual fusion mechanism -- the same technique
    RegimeAwareStrategyRouter already uses for regime-conditional
    reweighting (strategies/regime_router.py).

    fit() owns exactly the orchestration RuleForest/PatternMatcher
    themselves deliberately don't know about: building Triple-Barrier
    labels and ExpandedFeatureExtractor features from the last
    `training_bars` bars of a real bar history and handing each sub-model
    its own expected input shape. A sub-model that ends up with too few
    usable training rows simply stays unfitted (and is excluded from the
    vote) rather than failing the whole committee's fit -- the other
    sub-model can still function on its own.
    """

    name = "ml_committee"

    def __init__(
        self,
        *,
        rule_forest: RuleForest | None = None,
        pattern_matcher: PatternMatcher | None = None,
        feature_extractor: ExpandedFeatureExtractor | None = None,
        weight: float = DEFAULT_COMMITTEE_WEIGHT,
        neutral_band: float = 0.1,
    ) -> None:
        if not 0.0 < weight <= 1.0:
            raise ValueError("weight must be in (0.0, 1.0]")
        if not 0.0 <= neutral_band < 1.0:
            raise ValueError("neutral_band must be in [0.0, 1.0)")
        self._feature_extractor = feature_extractor or ExpandedFeatureExtractor()
        self._rule_forest = rule_forest or RuleForest(
            feature_names=self._feature_extractor.feature_names()
        )
        self._pattern_matcher = pattern_matcher or PatternMatcher()
        self._weight = weight
        self._neutral_band = neutral_band

    @property
    def is_fitted(self) -> bool:
        return self._rule_forest.is_fitted or self._pattern_matcher.is_fitted

    def fit(
        self,
        bars: Sequence[Bar],
        *,
        training_bars: int = 500,
        atr_period: int = 14,
        upper_multiple: float = 1.5,
        lower_multiple: float = 1.5,
        horizon: int = 20,
    ) -> None:
        window = list(bars[-training_bars:]) if len(bars) > training_bars else list(bars)
        labels = build_training_labels(
            window,
            atr_period=atr_period,
            upper_multiple=upper_multiple,
            lower_multiple=lower_multiple,
            horizon=horizon,
        )

        rule_forest_features: list[dict[str, float]] = []
        rule_forest_labels: list[int] = []
        for entry_index, label in labels:
            context = MarketContext(
                symbol=window[entry_index].symbol, bars=tuple(window[: entry_index + 1])
            )
            features = self._feature_extractor.extract(context)
            if features is None:
                continue
            rule_forest_features.append(features)
            rule_forest_labels.append(label.label)

        # Not enough usable rows this cycle -- the sub-model simply stays
        # unfitted and is excluded from the vote in analyze().
        with contextlib.suppress(ValueError):
            self._rule_forest.fit(rule_forest_features, rule_forest_labels)
        with contextlib.suppress(ValueError):
            self._pattern_matcher.fit(window, horizon=horizon)

    def analyze(self, context: MarketContext) -> list[Evidence]:
        if not self.is_fitted:
            return []

        votes: list[tuple[float, float]] = []
        if self._rule_forest.is_fitted:
            features = self._feature_extractor.extract(context)
            if features is not None:
                rule_forest_prediction = self._rule_forest.predict(features)
                if rule_forest_prediction is not None:
                    votes.append(
                        (rule_forest_prediction.probability, rule_forest_prediction.confidence)
                    )
        if self._pattern_matcher.is_fitted:
            pattern_prediction = self._pattern_matcher.predict(context.bars)
            if pattern_prediction is not None:
                votes.append((pattern_prediction.probability, pattern_prediction.confidence))

        if not votes:
            return []

        combined_probability = sum(probability for probability, _confidence in votes) / len(votes)
        if abs(combined_probability) < self._neutral_band:
            return []

        confidence = min(abs(combined_probability) * self._weight, 1.0)
        if confidence <= 0.0:
            return []

        direction = Direction.LONG if combined_probability > 0 else Direction.SHORT
        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={
                    "combined_probability": combined_probability,
                    "sub_model_votes": len(votes),
                    "weight": self._weight,
                },
            )
        ]


__all__ = ["DEFAULT_COMMITTEE_WEIGHT", "MLCommittee"]
