from __future__ import annotations

import pytest

from optimization.result import OptimizationResult, OptimizationTrial


def _trial(in_sample: float, out_of_sample: float, **params: float) -> OptimizationTrial:
    return OptimizationTrial(
        parameters=dict(params), in_sample_score=in_sample, out_of_sample_score=out_of_sample
    )


def test_degradation_is_none_when_in_sample_non_positive() -> None:
    trial = _trial(0.0, 5.0)
    assert trial.degradation is None

    trial_negative = _trial(-1.0, 5.0)
    assert trial_negative.degradation is None


def test_degradation_computed_correctly() -> None:
    trial = _trial(100.0, 60.0)
    assert trial.degradation == pytest.approx(0.4)

    trial_improved = _trial(50.0, 60.0)
    assert trial_improved.degradation == pytest.approx(-0.2)


def test_best_raises_on_empty_trials() -> None:
    result = OptimizationResult(trials=())

    with pytest.raises(ValueError):
        result.best()


def test_best_ranks_by_out_of_sample_score_not_in_sample() -> None:
    # Trial A has the higher in-sample score but the lower out-of-sample score;
    # a naive "pick the best in-sample" optimizer would choose A. best() must
    # choose B.
    trial_a = _trial(100.0, 10.0, period=5)
    trial_b = _trial(20.0, 18.0, period=20)
    result = OptimizationResult(trials=(trial_a, trial_b))

    assert result.best() is trial_b


def test_ranked_orders_all_trials_descending_by_out_of_sample_score() -> None:
    trial_low = _trial(10.0, 5.0)
    trial_mid = _trial(10.0, 10.0)
    trial_high = _trial(10.0, 15.0)
    result = OptimizationResult(trials=(trial_low, trial_high, trial_mid))

    assert result.ranked() == [trial_high, trial_mid, trial_low]


def test_best_within_degradation_excludes_overfit_trials() -> None:
    overfit = _trial(100.0, 10.0)  # degradation 0.9
    robust = _trial(20.0, 18.0)  # degradation 0.1

    result = OptimizationResult(trials=(overfit, robust))

    assert result.best_within_degradation(0.3) is robust


def test_best_within_degradation_raises_when_all_trials_are_overfit() -> None:
    overfit_a = _trial(100.0, 10.0)
    overfit_b = _trial(50.0, 5.0)
    result = OptimizationResult(trials=(overfit_a, overfit_b))

    with pytest.raises(ValueError):
        result.best_within_degradation(0.3)


def test_best_within_degradation_includes_trials_with_undefined_degradation() -> None:
    unprofitable_in_sample = _trial(-5.0, 2.0)  # degradation None
    result = OptimizationResult(trials=(unprofitable_in_sample,))

    assert result.best_within_degradation(0.1) is unprofitable_in_sample
