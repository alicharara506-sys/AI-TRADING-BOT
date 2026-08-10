from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from core.interfaces.types import Bar


@dataclass(frozen=True, slots=True)
class PatternMatch:
    start_index: int
    distance: float
    outcome_label: int  # +1 or -1: the realized direction after this historical window


@dataclass(frozen=True, slots=True)
class PatternMatcherPrediction:
    probability: float  # in [-1, 1]: fraction of k neighbors that moved up minus down
    confidence: float  # in [0, 1]: |probability|
    neighbors: tuple[PatternMatch, ...]


def _normalized_returns(bars: Sequence[Bar]) -> list[float]:
    """A window's bar-to-bar returns, z-score normalized within the window
    itself, so two windows with the same *shape* match closely regardless
    of the underlying price level or overall volatility scale -- the
    standard normalization for this kind of pattern-similarity search.
    Empty if fewer than 2 bars (nothing to take a return between)."""
    closes = [bar.close for bar in bars]
    returns = [
        (b - a) / a if a else 0.0 for a, b in zip(closes, closes[1:], strict=False)
    ]
    if not returns:
        return []
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    std = variance**0.5
    if std < 1e-12:
        return [0.0 for _ in returns]
    return [(value - mean) / std for value in returns]


def _euclidean_distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)))


class PatternMatcher:
    """K-nearest-neighbors over `window`-bar normalized-return sequences.

    `fit` records every historical `window`-bar slice found in the
    training bars, each tagged with the direction price actually moved
    over the following `horizon` bars (+1/-1); windows whose outcome was
    exactly flat, or smaller than `min_outcome_return`, are excluded --
    the same "exclude the ambiguous middle" principle Triple Barrier's
    horizontal label and RuleForest's own exclusion of it already apply.
    `predict` normalizes the most recent `window` bars the same way, finds
    the `k` closest historical windows by Euclidean distance over the
    normalized-return vectors, and votes: the fraction of the k nearest
    neighbors that moved up minus the fraction that moved down.

    A second, structurally different model from RuleForest (raw price-
    shape similarity vs. indicator-threshold splits) by design --
    MLCommittee (machine_learning/models/ml_committee.py) combines both
    because they can disagree in informative ways, not because either
    alone is expected to be sufficient.
    """

    def __init__(self, *, window: int = 20, k: int = 5) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")
        if k < 1:
            raise ValueError("k must be >= 1")
        self._window = window
        self._k = k
        self._patterns: list[tuple[list[float], int, int]] = []  # (returns, label, start_index)

    @property
    def is_fitted(self) -> bool:
        return len(self._patterns) >= self._k

    def fit(
        self, bars: Sequence[Bar], *, horizon: int = 20, min_outcome_return: float = 0.0
    ) -> None:
        if horizon < 1:
            raise ValueError("horizon must be >= 1")
        if min_outcome_return < 0:
            raise ValueError("min_outcome_return must be >= 0")

        self._patterns = []
        last_start = len(bars) - self._window - horizon
        for start in range(0, last_start + 1):
            window_bars = bars[start : start + self._window]
            normalized = _normalized_returns(window_bars)
            if not normalized:
                continue
            entry_close = window_bars[-1].close
            if entry_close <= 0:
                continue
            future_close = bars[start + self._window - 1 + horizon].close
            outcome_return = (future_close - entry_close) / entry_close
            if outcome_return == 0.0 or abs(outcome_return) < min_outcome_return:
                continue
            label = 1 if outcome_return > 0 else -1
            self._patterns.append((normalized, label, start))

    def predict(self, bars: Sequence[Bar]) -> PatternMatcherPrediction | None:
        if not self.is_fitted:
            return None
        if len(bars) < self._window:
            return None
        query = _normalized_returns(bars[-self._window :])
        if not query:
            return None

        scored = sorted(
            (
                PatternMatch(
                    start_index=start_index,
                    distance=_euclidean_distance(query, pattern),
                    outcome_label=label,
                )
                for pattern, label, start_index in self._patterns
            ),
            key=lambda match: match.distance,
        )
        neighbors = tuple(scored[: self._k])
        up = sum(1 for match in neighbors if match.outcome_label > 0)
        down = len(neighbors) - up
        probability = (up - down) / len(neighbors)
        return PatternMatcherPrediction(
            probability=probability, confidence=abs(probability), neighbors=neighbors
        )


__all__ = ["PatternMatch", "PatternMatcher", "PatternMatcherPrediction"]
