from __future__ import annotations

import numpy as np
import pytest

from machine_learning.models.calibrated_classifier import CalibratedClassifier

_FEATURE_NAMES = ["return_1", "sma_distance", "ema_distance", "rsi", "volatility"]


def _synthetic_dataset(*, n: int = 200, seed: int = 0) -> tuple[list[dict[str, float]], list[int]]:
    """Labels correlate with return_1's sign; other features are pure noise.
    A real, fittable, non-trivial classification problem, not a lookup table.
    """
    rng = np.random.default_rng(seed)
    features: list[dict[str, float]] = []
    labels: list[int] = []
    for _ in range(n):
        r = float(rng.normal(0, 0.01))
        features.append(
            {
                "return_1": r,
                "sma_distance": float(rng.normal(0, 0.01)),
                "ema_distance": float(rng.normal(0, 0.01)),
                "rsi": float(rng.uniform(30, 70)),
                "volatility": float(rng.uniform(0.001, 0.02)),
            }
        )
        labels.append(1 if r > 0 else 0)
    return features, labels


def test_rejects_empty_feature_names() -> None:
    with pytest.raises(ValueError):
        CalibratedClassifier(feature_names=[])


def test_predict_before_fit_raises() -> None:
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES)

    with pytest.raises(RuntimeError):
        model.predict_proba_long({name: 0.0 for name in _FEATURE_NAMES})


def test_fit_rejects_mismatched_lengths() -> None:
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES)
    features, labels = _synthetic_dataset(n=20)

    with pytest.raises(ValueError):
        model.fit(features, labels[:-1])


def test_fit_rejects_too_few_examples() -> None:
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES)
    features, labels = _synthetic_dataset(n=5)

    with pytest.raises(ValueError):
        model.fit(features, labels)


def test_fit_rejects_single_class_labels() -> None:
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES)
    features, _ = _synthetic_dataset(n=20)

    with pytest.raises(ValueError):
        model.fit(features, [1] * 20)


def test_is_fitted_reflects_state() -> None:
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES)
    assert model.is_fitted is False

    features, labels = _synthetic_dataset()
    model.fit(features, labels)
    assert model.is_fitted is True


def test_predicted_probability_tracks_the_predictive_feature() -> None:
    # Verified empirically: with feature scaling, a strongly positive
    # return_1 predicts LONG with high confidence, and vice versa.
    model = CalibratedClassifier(feature_names=_FEATURE_NAMES, random_state=0)
    features, labels = _synthetic_dataset()
    model.fit(features, labels)

    base = {"sma_distance": 0.0, "ema_distance": 0.0, "rsi": 50.0, "volatility": 0.01}
    probability_up = model.predict_proba_long({**base, "return_1": 0.02})
    probability_down = model.predict_proba_long({**base, "return_1": -0.02})

    assert probability_up > 0.9
    assert probability_down < 0.1
