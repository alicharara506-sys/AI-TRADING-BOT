from __future__ import annotations

import pytest

from core.interfaces.types import Direction, Evidence, Symbol
from core.signal.fusion import SignalFusion

_SYMBOL = Symbol(name="EURUSD")


def _evidence(direction: Direction, confidence: float, source: str = "test") -> Evidence:
    return Evidence(source_module=source, direction=direction, confidence=confidence)


def test_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        SignalFusion(threshold=0.4)
    with pytest.raises(ValueError):
        SignalFusion(threshold=1.0)


def test_empty_evidence_produces_no_signal() -> None:
    fusion = SignalFusion(threshold=0.6)

    assert fusion.fuse(_SYMBOL, []) is None


def test_empty_evidence_produces_no_signal_even_at_threshold_exactly_half() -> None:
    # Zero evidence yields exactly 0.5 combined probability, which a threshold of
    # exactly 0.5 (a valid configuration) would not reject on its own -- the
    # empty-evidence guard must catch this regardless of the threshold chosen.
    fusion = SignalFusion(threshold=0.5)

    assert fusion.fuse(_SYMBOL, []) is None


def test_single_evidence_combined_confidence_equals_its_own_confidence() -> None:
    # logit followed by sigmoid is the identity: with exactly one Evidence, the
    # combined probability must reproduce that Evidence's confidence exactly.
    fusion = SignalFusion(threshold=0.5)

    signal = fusion.fuse(_SYMBOL, [_evidence(Direction.LONG, 0.9)])

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.combined_confidence == pytest.approx(0.9)


def test_single_evidence_below_threshold_produces_no_signal() -> None:
    fusion = SignalFusion(threshold=0.9)

    assert fusion.fuse(_SYMBOL, [_evidence(Direction.LONG, 0.7)]) is None


def test_agreeing_evidence_reinforces_above_either_alone() -> None:
    fusion = SignalFusion(threshold=0.5)

    combined = fusion.fuse(
        _SYMBOL,
        [_evidence(Direction.LONG, 0.6, "a"), _evidence(Direction.LONG, 0.6, "b")],
    )

    assert combined is not None
    assert combined.direction == Direction.LONG
    assert combined.combined_confidence > 0.6


def test_exactly_opposing_evidence_cancels_to_no_signal() -> None:
    fusion = SignalFusion(threshold=0.6)

    result = fusion.fuse(
        _SYMBOL,
        [_evidence(Direction.LONG, 0.8, "a"), _evidence(Direction.SHORT, 0.8, "b")],
    )

    assert result is None  # equal-and-opposite log-odds cancel to exactly 0.5


def test_neutral_evidence_contributes_nothing() -> None:
    fusion = SignalFusion(threshold=0.5)

    with_neutral = fusion.fuse(
        _SYMBOL,
        [_evidence(Direction.LONG, 0.9, "a"), _evidence(Direction.NEUTRAL, 0.99, "b")],
    )
    without_neutral = fusion.fuse(_SYMBOL, [_evidence(Direction.LONG, 0.9, "a")])

    assert with_neutral is not None
    assert without_neutral is not None
    assert with_neutral.combined_confidence == pytest.approx(without_neutral.combined_confidence)


def test_signal_carries_full_evidence_trail() -> None:
    fusion = SignalFusion(threshold=0.5)
    evidence = [_evidence(Direction.LONG, 0.9, "a"), _evidence(Direction.LONG, 0.6, "b")]

    signal = fusion.fuse(_SYMBOL, evidence)

    assert signal is not None
    assert signal.evidence == tuple(evidence)


class _FakeReliabilityProvider:
    def __init__(self, rates: dict[tuple[str, str], float]) -> None:
        self._rates = rates

    def hit_rate(self, module_name: str, symbol: str) -> float | None:
        return self._rates.get((module_name, symbol))


def test_no_reliability_provider_behaves_exactly_as_before() -> None:
    fusion = SignalFusion(threshold=0.6)

    signal = fusion.fuse(_SYMBOL, [_evidence(Direction.LONG, 0.8, "m1")])

    assert signal is not None
    assert signal.combined_confidence == pytest.approx(0.8)


def test_provider_with_no_history_for_a_module_behaves_as_full_weight() -> None:
    baseline = SignalFusion(threshold=0.6).fuse(_SYMBOL, [_evidence(Direction.LONG, 0.8, "m1")])
    weighted = SignalFusion(
        threshold=0.6, reliability_provider=_FakeReliabilityProvider({})
    ).fuse(_SYMBOL, [_evidence(Direction.LONG, 0.8, "m1")])

    assert baseline is not None
    assert weighted is not None
    assert weighted.combined_confidence == pytest.approx(baseline.combined_confidence)


def test_perfect_hit_rate_keeps_full_weight() -> None:
    provider = _FakeReliabilityProvider({("m1", "EURUSD"): 1.0})
    fusion = SignalFusion(threshold=0.6, reliability_provider=provider)

    signal = fusion.fuse(_SYMBOL, [_evidence(Direction.LONG, 0.8, "m1")])

    assert signal is not None
    assert signal.combined_confidence == pytest.approx(0.8)


def test_coin_flip_hit_rate_zeroes_the_module_out() -> None:
    provider = _FakeReliabilityProvider({("m1", "EURUSD"): 0.5})
    fusion = SignalFusion(threshold=0.6, reliability_provider=provider)

    signal = fusion.fuse(_SYMBOL, [_evidence(Direction.LONG, 0.8, "m1")])

    assert signal is None  # zeroed contribution never reaches any threshold > 0.5


def test_zero_hit_rate_inverts_the_modules_direction() -> None:
    """A module wrong 100% of the time is exactly as informative as one
    right 100% of the time -- its contribution is inverted, not discarded.
    """
    provider = _FakeReliabilityProvider({("m1", "EURUSD"): 0.0})
    fusion = SignalFusion(threshold=0.6, reliability_provider=provider)

    signal = fusion.fuse(_SYMBOL, [_evidence(Direction.LONG, 0.8, "m1")])

    assert signal is not None
    assert signal.direction == Direction.SHORT
    assert signal.combined_confidence == pytest.approx(0.8)


def test_unreliable_module_no_longer_dominates_a_reliable_one() -> None:
    """Without weighting, the noisier module's higher raw confidence wins.
    With weighting, its lack of a real track record correctly demotes it.
    """
    evidence = [
        _evidence(Direction.LONG, 0.7, "reliable"),
        _evidence(Direction.SHORT, 0.9, "noisy"),
    ]
    unweighted = SignalFusion(threshold=0.5).fuse(_SYMBOL, evidence)
    assert unweighted is not None
    assert unweighted.direction == Direction.SHORT

    provider = _FakeReliabilityProvider({("reliable", "EURUSD"): 0.95, ("noisy", "EURUSD"): 0.5})
    weighted = SignalFusion(threshold=0.5, reliability_provider=provider).fuse(_SYMBOL, evidence)

    assert weighted is not None
    assert weighted.direction == Direction.LONG
