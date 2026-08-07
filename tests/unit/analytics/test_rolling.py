from __future__ import annotations

import pytest

from analytics import metrics
from analytics.rolling import compute_rolling_metric


def test_rolling_total_return_matches_hand_computed_windows() -> None:
    returns = [1.0, 2.0, 3.0, 4.0, 5.0]

    rolling = compute_rolling_metric(returns, window=3, metric_fn=metrics.total_return)

    # windows: [1,2,3]=6, [2,3,4]=9, [3,4,5]=12
    assert rolling == pytest.approx([6.0, 9.0, 12.0])


def test_rolling_metric_reuses_any_metrics_function() -> None:
    returns = [10, -5, 10, -5, 10, -5, 10, -5]

    rolling = compute_rolling_metric(returns, window=4, metric_fn=metrics.max_drawdown)

    assert len(rolling) == len(returns) - 4 + 1
    assert all(value == pytest.approx(5.0) for value in rolling)


def test_rolling_metric_returns_empty_list_without_a_full_window() -> None:
    assert compute_rolling_metric([1.0, 2.0], window=5, metric_fn=metrics.total_return) == []


def test_rolling_metric_with_window_equal_to_full_length_returns_one_value() -> None:
    returns = [1.0, 2.0, 3.0]

    rolling = compute_rolling_metric(returns, window=3, metric_fn=metrics.total_return)

    assert rolling == pytest.approx([6.0])


def test_rejects_invalid_window() -> None:
    with pytest.raises(ValueError):
        compute_rolling_metric([1.0, 2.0, 3.0], window=0, metric_fn=metrics.total_return)
