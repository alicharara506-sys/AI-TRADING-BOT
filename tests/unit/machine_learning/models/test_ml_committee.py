from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from machine_learning.models.ml_committee import MLCommittee
from machine_learning.models.pattern_matcher import PatternMatcherPrediction
from machine_learning.models.rule_forest import RuleForestPrediction

_SYMBOL = Symbol(name="EURUSD")


def _bars(count: int) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=100.0 + 0.01 * (i % 7),
            high=100.5 + 0.01 * (i % 7),
            low=99.5 + 0.01 * (i % 7),
            close=100.0 + 0.02 * ((i * 3) % 11) - 0.01 * (i % 5),
            volume=1.0 + (i % 4),
        )
        for i in range(count)
    ]


def _context(count: int = 3) -> MarketContext:
    return MarketContext(symbol=_SYMBOL, bars=tuple(_bars(count)))


class _FakeSubModel:
    def __init__(self, *, fitted: bool, probability: float = 0.0, confidence: float = 0.0) -> None:
        self.is_fitted = fitted
        self._probability = probability
        self._confidence = confidence

    def predict(self, _query: object) -> object:
        return None


class _FakeRuleForest(_FakeSubModel):
    def predict(self, _features: dict[str, float]) -> RuleForestPrediction | None:
        if not self.is_fitted:
            return None
        return RuleForestPrediction(probability=self._probability, confidence=self._confidence)


class _FakePatternMatcher(_FakeSubModel):
    def predict(self, _bars: object) -> PatternMatcherPrediction | None:
        if not self.is_fitted:
            return None
        return PatternMatcherPrediction(
            probability=self._probability, confidence=self._confidence, neighbors=()
        )


class _FakeFeatureExtractor:
    """Always succeeds regardless of how many bars context carries -- lets
    tests exercise MLCommittee's vote-combination logic without needing
    the real ExpandedFeatureExtractor's ~114-bar minimum history."""

    def feature_names(self) -> list[str]:
        return ["dummy"]

    def extract(self, _context: MarketContext) -> dict[str, float]:
        return {"dummy": 0.0}


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        MLCommittee(weight=0.0)
    with pytest.raises(ValueError):
        MLCommittee(weight=1.1)
    with pytest.raises(ValueError):
        MLCommittee(neutral_band=1.0)


def test_not_fitted_before_fit_produces_no_evidence() -> None:
    committee = MLCommittee(
        rule_forest=_FakeRuleForest(fitted=False),  # type: ignore[arg-type]
        pattern_matcher=_FakePatternMatcher(fitted=False),  # type: ignore[arg-type]
    )

    assert committee.is_fitted is False
    assert committee.analyze(_context()) == []


def test_agreeing_sub_models_produce_scaled_long_evidence() -> None:
    committee = MLCommittee(
        rule_forest=_FakeRuleForest(fitted=True, probability=0.8, confidence=0.8),  # type: ignore[arg-type]
        pattern_matcher=_FakePatternMatcher(fitted=True, probability=0.6, confidence=0.6),  # type: ignore[arg-type]
        feature_extractor=_FakeFeatureExtractor(),  # type: ignore[arg-type]
        weight=0.15,
        neutral_band=0.1,
    )

    evidence = committee.analyze(_context())

    assert len(evidence) == 1
    assert evidence[0].direction is Direction.LONG
    # combined_probability = (0.8 + 0.6) / 2 = 0.7 -> confidence = 0.7 * 0.15
    assert evidence[0].confidence == pytest.approx(0.7 * 0.15)


def test_agreeing_sub_models_produce_scaled_short_evidence() -> None:
    committee = MLCommittee(
        rule_forest=_FakeRuleForest(fitted=True, probability=-0.9, confidence=0.9),  # type: ignore[arg-type]
        pattern_matcher=_FakePatternMatcher(fitted=False),  # type: ignore[arg-type]
        feature_extractor=_FakeFeatureExtractor(),  # type: ignore[arg-type]
        weight=0.15,
        neutral_band=0.1,
    )

    evidence = committee.analyze(_context())

    assert len(evidence) == 1
    assert evidence[0].direction is Direction.SHORT
    assert evidence[0].confidence == pytest.approx(0.9 * 0.15)


def test_weak_combined_probability_within_neutral_band_abstains() -> None:
    committee = MLCommittee(
        rule_forest=_FakeRuleForest(fitted=True, probability=0.05, confidence=0.05),  # type: ignore[arg-type]
        pattern_matcher=_FakePatternMatcher(fitted=False),  # type: ignore[arg-type]
        neutral_band=0.1,
    )

    assert committee.analyze(_context()) == []


def test_fit_and_analyze_end_to_end_never_raises() -> None:
    committee = MLCommittee()
    bars = _bars(220)

    committee.fit(bars, training_bars=220, horizon=10)
    evidence = committee.analyze(MarketContext(symbol=_SYMBOL, bars=tuple(bars)))

    assert isinstance(evidence, list)
    for item in evidence:
        assert item.source_module == "ml_committee"
        assert 0.0 <= item.confidence <= 1.0
