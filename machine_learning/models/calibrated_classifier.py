from __future__ import annotations

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler


class CalibratedClassifier:
    """A probability-calibrated binary classifier for LONG (1) vs SHORT (0).
    Logistic regression is calibrated by construction -- its output is
    literally a modeled probability, not a score requiring separate
    calibration -- satisfying the architecture's requirement that ML
    predictions feed Evidence via a real calibrated probability rather than
    an arbitrary confidence heuristic.

    Features are standardized before fitting: our feature set mixes wildly
    different scales (a return around 0.01 next to an RSI around 50), and
    unscaled L2-regularized logistic regression systematically underweights
    the smaller-scale features rather than judging them on predictive merit.
    """

    def __init__(self, *, feature_names: list[str], random_state: int | None = None) -> None:
        if not feature_names:
            raise ValueError("feature_names must not be empty")
        self._feature_names = list(feature_names)
        self._model: Pipeline = make_pipeline(
            StandardScaler(), LogisticRegression(random_state=random_state)
        )
        self._fitted = False

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(self, features: list[dict[str, float]], labels: list[int]) -> None:
        if len(features) != len(labels):
            raise ValueError("features and labels must be the same length")
        if len(features) < 10:
            raise ValueError("need at least 10 training examples")
        if len(set(labels)) < 2:
            raise ValueError("training labels must include both classes")
        design_matrix = [[row[name] for name in self._feature_names] for row in features]
        self._model.fit(design_matrix, labels)
        self._fitted = True

    def predict_proba_long(self, features: dict[str, float]) -> float:
        """Returns the calibrated probability of the LONG class (label 1)."""
        if not self._fitted:
            raise RuntimeError("model is not fitted yet")
        row = [[features[name] for name in self._feature_names]]
        probabilities = self._model.predict_proba(row)[0]
        long_index = list(self._model.classes_).index(1)
        return float(probabilities[long_index])


__all__ = ["CalibratedClassifier"]
