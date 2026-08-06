from __future__ import annotations

from core.interfaces.types import Direction, Evidence, MarketContext
from machine_learning.features.extractor import FeatureExtractor
from machine_learning.models.calibrated_classifier import CalibratedClassifier


class MLPredictionModule:
    """Wraps a trained CalibratedClassifier as an AnalysisModule: a model's
    prediction becomes Evidence exactly like every other analytical layer,
    with confidence taken directly from the model's own calibrated
    probability output -- never a fabricated number. Emits nothing (rather
    than a low-confidence guess) when the model isn't fitted yet, or when its
    own probability is too close to 0.5 to represent a real directional call.
    """

    name = "ml_prediction"

    def __init__(
        self,
        model: CalibratedClassifier,
        feature_extractor: FeatureExtractor,
        *,
        neutral_band: float = 0.1,
    ) -> None:
        if not 0.0 <= neutral_band < 0.5:
            raise ValueError("neutral_band must be in [0, 0.5)")
        self._model = model
        self._feature_extractor = feature_extractor
        self._neutral_band = neutral_band

    def analyze(self, context: MarketContext) -> list[Evidence]:
        if not self._model.is_fitted:
            return []

        features = self._feature_extractor.extract(context)
        if features is None:
            return []

        probability_long = self._model.predict_proba_long(features)
        if abs(probability_long - 0.5) < self._neutral_band:
            return []

        direction = Direction.LONG if probability_long > 0.5 else Direction.SHORT
        confidence = probability_long if direction is Direction.LONG else 1.0 - probability_long

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={"probability_long": probability_long},
                supporting_data=dict(features),
            )
        ]


__all__ = ["MLPredictionModule"]
