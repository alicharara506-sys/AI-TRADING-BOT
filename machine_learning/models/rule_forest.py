from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

_MIN_TRAINING_EXAMPLES = 10


@dataclass(frozen=True, slots=True)
class DecisionStump:
    """A single-split tree: votes `direction` when feature[feature_name] is
    above `threshold`, `-direction` otherwise. `accuracy` is this stump's
    own training-set accuracy, used as its voting weight in the ensemble."""

    feature_name: str
    threshold: float
    direction: int
    accuracy: float


@dataclass(frozen=True, slots=True)
class RuleForestPrediction:
    probability: float  # in [-1, 1]: accuracy-weighted vote share, up minus down
    confidence: float  # in [0, 1]: |probability| -- how lopsided the vote was


class RuleForest:
    """A lightweight, fully pure-Python ensemble of `n_stumps` decision
    stumps (single feature + threshold splits) voting on direction --
    deliberately not sklearn's RandomForest or TensorFlow.js: this
    platform's existing ML classifier (CalibratedClassifier,
    machine_learning/models/calibrated_classifier.py) already covers a
    full-featured, properly-calibrated sklearn model. RuleForest is a
    second, much simpler, fully-inspectable model -- every one of its
    votes can be printed as a literal "feature > threshold" rule -- meant
    to be retrained fresh on a short, recent window rather than a long,
    possibly stale history.

    Mirrors CalibratedClassifier's own fit(features, labels) /
    predict(features) contract (feature_names fixed at construction, plain
    dict-of-floats rows) rather than knowing anything about bars, ATR, or
    the Triple Barrier Method itself -- exactly how CalibratedClassifier
    stays decoupled from MarketContext. Building the "last 500 bars,
    Triple-Barrier-labeled" training set is the caller's job (see
    machine_learning/models/ml_committee.py), using
    machine_learning.labeling.triple_barrier.build_training_labels and an
    ExpandedFeatureExtractor.

    Each stump is fit by sampling one feature and scanning every candidate
    split (a midpoint between two consecutive observed values of that
    feature) for whichever threshold+direction combination best separates
    up-moves (label +1) from down-moves (label -1) in the training rows;
    horizontal-barrier rows (label 0, i.e. "neither barrier hit") are
    excluded before fitting, since a stump votes up/down and has nothing
    useful to say about a barrier that was never touched. Prediction is a
    majority vote across all fitted stumps, weighted by each stump's own
    training-set accuracy.
    """

    def __init__(
        self,
        *,
        feature_names: Sequence[str],
        n_stumps: int = 50,
        random_seed: int | None = None,
    ) -> None:
        if not feature_names:
            raise ValueError("feature_names must not be empty")
        if n_stumps < 1:
            raise ValueError("n_stumps must be >= 1")
        self._feature_names = list(feature_names)
        self._n_stumps = n_stumps
        self._random = random.Random(random_seed)
        self._stumps: list[DecisionStump] = []

    @property
    def is_fitted(self) -> bool:
        return len(self._stumps) > 0

    def fit(self, features: list[dict[str, float]], labels: list[int]) -> None:
        if len(features) != len(labels):
            raise ValueError("features and labels must be the same length")
        rows = [
            (row, label) for row, label in zip(features, labels, strict=True) if label != 0
        ]
        if len(rows) < _MIN_TRAINING_EXAMPLES:
            raise ValueError(f"need at least {_MIN_TRAINING_EXAMPLES} non-horizontal examples")
        if len({label for _row, label in rows}) < 2:
            raise ValueError("training labels must include both up (+1) and down (-1) examples")

        self._stumps = [
            stump
            for stump in (
                self._fit_one_stump(rows, self._random.choice(self._feature_names))
                for _ in range(self._n_stumps)
            )
            if stump is not None
        ]

    def predict(self, features: dict[str, float]) -> RuleForestPrediction | None:
        if not self.is_fitted:
            return None

        weighted_up = 0.0
        weighted_down = 0.0
        for stump in self._stumps:
            vote = (
                stump.direction
                if features[stump.feature_name] > stump.threshold
                else -stump.direction
            )
            if vote > 0:
                weighted_up += stump.accuracy
            else:
                weighted_down += stump.accuracy

        total = weighted_up + weighted_down
        if total <= 0:
            return RuleForestPrediction(probability=0.0, confidence=0.0)
        probability = (weighted_up - weighted_down) / total
        return RuleForestPrediction(probability=probability, confidence=abs(probability))

    def _fit_one_stump(
        self, rows: list[tuple[dict[str, float], int]], feature_name: str
    ) -> DecisionStump | None:
        values = sorted({row[feature_name] for row, _label in rows})
        if len(values) < 2:
            return None
        candidates = [(a + b) / 2 for a, b in zip(values, values[1:], strict=False)]

        best: DecisionStump | None = None
        for threshold in candidates:
            for direction in (1, -1):
                correct = sum(
                    1
                    for row, label in rows
                    if (direction if row[feature_name] > threshold else -direction) == label
                )
                accuracy = correct / len(rows)
                if best is None or accuracy > best.accuracy:
                    best = DecisionStump(
                        feature_name=feature_name,
                        threshold=threshold,
                        direction=direction,
                        accuracy=accuracy,
                    )
        return best


__all__ = ["DecisionStump", "RuleForest", "RuleForestPrediction"]
