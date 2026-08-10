from __future__ import annotations

import pytest

from machine_learning.models.rule_forest import RuleForest


def _perfectly_separable_dataset(n: int = 20) -> tuple[list[dict[str, float]], list[int]]:
    """`signal` alone perfectly determines the label: positive -> up,
    negative -> down. `noise` is uncorrelated, present so a fitted forest
    has more than one feature to (correctly) ignore."""
    features: list[dict[str, float]] = []
    labels: list[int] = []
    for i in range(n):
        signal = 1.0 if i % 2 == 0 else -1.0
        features.append({"signal": signal, "noise": float((i * 7) % 5)})
        labels.append(1 if signal > 0 else -1)
    return features, labels


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        RuleForest(feature_names=[])
    with pytest.raises(ValueError):
        RuleForest(feature_names=["a"], n_stumps=0)


def test_is_not_fitted_before_fit_is_called() -> None:
    forest = RuleForest(feature_names=["signal"], random_seed=1)
    assert forest.is_fitted is False
    assert forest.predict({"signal": 1.0}) is None


def test_fit_rejects_mismatched_lengths() -> None:
    forest = RuleForest(feature_names=["signal"], random_seed=1)
    with pytest.raises(ValueError):
        forest.fit([{"signal": 1.0}], [1, -1])


def test_fit_rejects_too_few_non_horizontal_examples() -> None:
    forest = RuleForest(feature_names=["signal"], random_seed=1)
    features = [{"signal": 1.0}] * 3
    labels = [1, -1, 1]
    with pytest.raises(ValueError):
        forest.fit(features, labels)


def test_fit_rejects_a_single_class() -> None:
    forest = RuleForest(feature_names=["signal"], random_seed=1)
    features, _labels = _perfectly_separable_dataset(20)
    labels = [1] * 20
    with pytest.raises(ValueError):
        forest.fit(features, labels)


def test_fit_excludes_horizontal_zero_labels() -> None:
    forest = RuleForest(feature_names=["signal", "noise"], n_stumps=20, random_seed=1)
    features, labels = _perfectly_separable_dataset(20)
    # Interleave a batch of horizontal (label 0) rows that must be ignored.
    features += [{"signal": 0.0, "noise": 1.0}] * 5
    labels += [0] * 5

    forest.fit(features, labels)

    assert forest.is_fitted is True


def test_predicts_correctly_on_a_perfectly_separable_dataset() -> None:
    forest = RuleForest(feature_names=["signal", "noise"], n_stumps=30, random_seed=1)
    features, labels = _perfectly_separable_dataset(20)

    forest.fit(features, labels)
    up_prediction = forest.predict({"signal": 1.0, "noise": 2.0})
    down_prediction = forest.predict({"signal": -1.0, "noise": 2.0})

    assert up_prediction is not None and up_prediction.probability > 0.3
    assert up_prediction.confidence > 0.3
    assert down_prediction is not None and down_prediction.probability < -0.3


def test_probability_and_confidence_stay_within_declared_bounds() -> None:
    forest = RuleForest(feature_names=["signal", "noise"], n_stumps=30, random_seed=2)
    features, labels = _perfectly_separable_dataset(20)
    forest.fit(features, labels)

    for row in features:
        prediction = forest.predict(row)
        assert prediction is not None
        assert -1.0 <= prediction.probability <= 1.0
        assert 0.0 <= prediction.confidence <= 1.0


def test_same_seed_produces_deterministic_stumps() -> None:
    features, labels = _perfectly_separable_dataset(20)
    forest_a = RuleForest(feature_names=["signal", "noise"], n_stumps=10, random_seed=42)
    forest_b = RuleForest(feature_names=["signal", "noise"], n_stumps=10, random_seed=42)

    forest_a.fit(features, labels)
    forest_b.fit(features, labels)

    prediction_a = forest_a.predict({"signal": 1.0, "noise": 3.0})
    prediction_b = forest_b.predict({"signal": 1.0, "noise": 3.0})
    assert prediction_a == prediction_b
