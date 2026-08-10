from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Symbol, Timeframe
from machine_learning.models.pattern_matcher import PatternMatcher

_SYMBOL = Symbol(name="EURUSD")

_WINDOW = 5
_HORIZON = 3
# 4 "shape" returns (window - 1) followed by 3 strongly-positive "horizon
# continuation" returns -- one repeating cycle used to build a series whose
# net drift over any window+horizon slice is unambiguously in one direction.
_UP_CYCLE = [0.01, -0.005, 0.02, -0.005, 0.03, 0.03, 0.03]
_DOWN_CYCLE = [-r for r in _UP_CYCLE]


def _closes_from_cycle(
    cycle: list[float], repeats: int, *, start_price: float = 100.0
) -> list[float]:
    closes = [start_price]
    for _ in range(repeats):
        for r in cycle:
            closes.append(closes[-1] * (1 + r))
    return closes


def _bars_from_closes(closes: list[float]) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1.0,
        )
        for i, close in enumerate(closes)
    ]


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        PatternMatcher(window=1)
    with pytest.raises(ValueError):
        PatternMatcher(window=5, k=0)


def test_not_fitted_before_fit_or_with_too_few_patterns() -> None:
    matcher = PatternMatcher(window=_WINDOW, k=100)
    bars = _bars_from_closes(_closes_from_cycle(_UP_CYCLE, repeats=6))

    matcher.fit(bars, horizon=_HORIZON)

    assert matcher.is_fitted is False
    assert matcher.predict(bars) is None


def test_fit_rejects_invalid_parameters() -> None:
    matcher = PatternMatcher(window=_WINDOW, k=3)
    bars = _bars_from_closes(_closes_from_cycle(_UP_CYCLE, repeats=6))
    with pytest.raises(ValueError):
        matcher.fit(bars, horizon=0)
    with pytest.raises(ValueError):
        matcher.fit(bars, min_outcome_return=-0.1)


def test_predict_returns_none_with_fewer_bars_than_window() -> None:
    matcher = PatternMatcher(window=_WINDOW, k=3)
    bars = _bars_from_closes(_closes_from_cycle(_UP_CYCLE, repeats=6))
    matcher.fit(bars, horizon=_HORIZON)

    assert matcher.predict(bars[:2]) is None


def test_predicts_up_for_a_query_matching_the_up_shaped_training_data() -> None:
    up_bars = _bars_from_closes(_closes_from_cycle(_UP_CYCLE, repeats=6))
    down_bars = _bars_from_closes(_closes_from_cycle(_DOWN_CYCLE, repeats=6))[1:]
    combined = up_bars + down_bars
    matcher = PatternMatcher(window=_WINDOW, k=3)
    matcher.fit(combined, horizon=_HORIZON)

    query = _bars_from_closes(_closes_from_cycle(_UP_CYCLE, repeats=1))[:_WINDOW]
    prediction = matcher.predict(query)

    assert prediction is not None
    assert prediction.probability == pytest.approx(1.0)
    assert prediction.confidence == pytest.approx(1.0)
    assert all(neighbor.outcome_label == 1 for neighbor in prediction.neighbors)


def test_predicts_down_for_a_query_matching_the_down_shaped_training_data() -> None:
    up_bars = _bars_from_closes(_closes_from_cycle(_UP_CYCLE, repeats=6))
    down_bars = _bars_from_closes(_closes_from_cycle(_DOWN_CYCLE, repeats=6))[1:]
    combined = up_bars + down_bars
    matcher = PatternMatcher(window=_WINDOW, k=3)
    matcher.fit(combined, horizon=_HORIZON)

    query = _bars_from_closes(_closes_from_cycle(_DOWN_CYCLE, repeats=1))[:_WINDOW]
    prediction = matcher.predict(query)

    assert prediction is not None
    assert prediction.probability == pytest.approx(-1.0)
    assert all(neighbor.outcome_label == -1 for neighbor in prediction.neighbors)


def test_fit_excludes_exactly_flat_outcomes() -> None:
    flat_closes = [100.0] * 20
    matcher = PatternMatcher(window=_WINDOW, k=1)
    matcher.fit(_bars_from_closes(flat_closes), horizon=_HORIZON)

    assert matcher.is_fitted is False
