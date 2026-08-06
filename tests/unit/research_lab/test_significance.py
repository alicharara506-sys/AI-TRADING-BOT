from __future__ import annotations

import random

import pytest

from research_lab.significance import welch_t_test


def test_identically_distributed_samples_are_not_significant() -> None:
    rng = random.Random(0)
    baseline = [rng.gauss(0, 1) for _ in range(30)]
    candidate = [rng.gauss(0, 1) for _ in range(30)]

    result = welch_t_test(baseline, candidate)

    assert result.significant is False
    assert result.p_value > 0.05


def test_clearly_shifted_samples_are_significant() -> None:
    rng = random.Random(0)
    baseline = [rng.gauss(0, 1) for _ in range(30)]
    candidate = [rng.gauss(2.0, 1) for _ in range(30)]

    result = welch_t_test(baseline, candidate)

    assert result.significant is True
    assert result.p_value < 0.05


def test_rejects_samples_smaller_than_two() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        welch_t_test([1.0], [1.0, 2.0])


def test_rejects_invalid_alpha() -> None:
    with pytest.raises(ValueError, match="alpha"):
        welch_t_test([1.0, 2.0], [3.0, 4.0], alpha=1.5)
