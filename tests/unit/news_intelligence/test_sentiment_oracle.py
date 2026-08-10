from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Direction
from news_intelligence.sentiment_oracle import (
    LocalLLMConsensusEngine,
    SentimentConfirmationFilter,
    SentimentSpikeDetector,
)
from news_intelligence.types import NewsItem
from tests.support.fake_llm_provider import FakeLLMProvider

_HEADLINES = [
    NewsItem(
        item_id="1",
        source="test",
        headline="Gold rallies on rate-cut bets",
        body="",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
]


def _provider(response: str = "0.5") -> FakeLLMProvider:
    return FakeLLMProvider(next_response=response)


# ---- LocalLLMConsensusEngine -----------------------------------------------


def test_rejects_empty_providers() -> None:
    with pytest.raises(ValueError):
        LocalLLMConsensusEngine([])


async def test_consensus_averages_parseable_responses() -> None:
    engine = LocalLLMConsensusEngine([_provider("0.5"), _provider("-0.5"), _provider("1.0")])

    result = await engine.consensus_sentiment("XAUUSD", _HEADLINES)

    assert result == pytest.approx((0.5 - 0.5 + 1.0) / 3)


async def test_consensus_excludes_failing_providers_rather_than_zero_filling() -> None:
    engine = LocalLLMConsensusEngine(
        [_provider("1.0"), FakeLLMProvider(error=ConnectionError("refused"))]
    )

    result = await engine.consensus_sentiment("XAUUSD", _HEADLINES)

    # If the failed provider were silently zero-filled the average would be
    # 0.5, not 1.0 -- proving exclusion, not substitution.
    assert result == pytest.approx(1.0)


async def test_consensus_excludes_unparseable_responses() -> None:
    engine = LocalLLMConsensusEngine([_provider("1.0"), _provider("not a number")])

    result = await engine.consensus_sentiment("XAUUSD", _HEADLINES)

    assert result == pytest.approx(1.0)


async def test_consensus_is_none_when_every_provider_fails() -> None:
    engine = LocalLLMConsensusEngine(
        [FakeLLMProvider(error=TimeoutError()), _provider("garbage")]
    )

    assert await engine.consensus_sentiment("XAUUSD", _HEADLINES) is None


async def test_consensus_clamps_out_of_range_responses() -> None:
    engine = LocalLLMConsensusEngine([_provider("5.0")])

    result = await engine.consensus_sentiment("XAUUSD", _HEADLINES)

    assert result == pytest.approx(1.0)


async def test_consensus_prompt_includes_symbol_and_headlines() -> None:
    provider = _provider("0.0")
    engine = LocalLLMConsensusEngine([provider])

    await engine.consensus_sentiment("XAUUSD", _HEADLINES)

    assert "XAUUSD" in provider.prompts_received[0]
    assert "Gold rallies on rate-cut bets" in provider.prompts_received[0]


# ---- SentimentSpikeDetector -------------------------------------------------


def test_spike_detector_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        SentimentSpikeDetector(zscore_threshold=0.0)


def test_no_spike_with_fewer_than_two_samples() -> None:
    detector = SentimentSpikeDetector()
    detector.record(0.9, at=datetime(2026, 1, 1, tzinfo=UTC))
    assert detector.is_spike() is False


def test_spike_flagged_for_an_outlier_reading() -> None:
    detector = SentimentSpikeDetector(zscore_threshold=2.0)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(10):
        detector.record(0.0, at=base + timedelta(minutes=i))
    detector.record(0.9, at=base + timedelta(minutes=11))

    assert detector.is_spike() is True


def test_old_samples_fall_outside_the_rolling_window() -> None:
    detector = SentimentSpikeDetector(window=timedelta(hours=24), zscore_threshold=2.0)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    detector.record(0.9, at=base)
    detector.record(0.0, at=base + timedelta(hours=25))

    # The 0.9 reading has aged out of the 24h window, leaving only one
    # sample -- not enough for a z-score.
    assert detector.latest_zscore() is None


def test_no_spike_for_constant_readings() -> None:
    detector = SentimentSpikeDetector()
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(5):
        detector.record(0.3, at=base + timedelta(minutes=i))

    assert detector.is_spike() is False


# ---- SentimentConfirmationFilter -------------------------------------------


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        SentimentConfirmationFilter(long_floor=-2.0)
    with pytest.raises(ValueError):
        SentimentConfirmationFilter(short_ceiling=2.0)
    with pytest.raises(ValueError):
        SentimentConfirmationFilter(spike_threshold=-0.1)


def test_long_passes_at_or_above_the_floor() -> None:
    gate = SentimentConfirmationFilter(long_floor=-0.2)

    result = gate.evaluate(Direction.LONG, -0.2)

    assert result.passes is True
    assert result.confidence_boost == 0.0


def test_long_blocked_below_the_floor() -> None:
    gate = SentimentConfirmationFilter(long_floor=-0.2)

    result = gate.evaluate(Direction.LONG, -0.3)

    assert result.passes is False


def test_short_passes_at_or_below_the_ceiling() -> None:
    gate = SentimentConfirmationFilter(short_ceiling=0.2)

    result = gate.evaluate(Direction.SHORT, 0.2)

    assert result.passes is True


def test_short_blocked_above_the_ceiling() -> None:
    gate = SentimentConfirmationFilter(short_ceiling=0.2)

    result = gate.evaluate(Direction.SHORT, 0.3)

    assert result.passes is False


def test_aligned_spike_boosts_confidence() -> None:
    gate = SentimentConfirmationFilter(spike_threshold=0.7, spike_confidence_boost=0.05)

    result = gate.evaluate(Direction.LONG, 0.8)

    assert result.passes is True
    assert result.confidence_boost == pytest.approx(0.05)


def test_opposing_spike_blocks_long_even_though_it_would_otherwise_pass() -> None:
    gate = SentimentConfirmationFilter(long_floor=-0.9, spike_threshold=0.7)

    result = gate.evaluate(Direction.LONG, -0.8)

    assert result.passes is False


def test_opposing_spike_blocks_short_even_though_it_would_otherwise_pass() -> None:
    gate = SentimentConfirmationFilter(short_ceiling=0.9, spike_threshold=0.7)

    result = gate.evaluate(Direction.SHORT, 0.8)

    assert result.passes is False


def test_neutral_direction_always_passes_with_no_boost() -> None:
    gate = SentimentConfirmationFilter()

    result = gate.evaluate(Direction.NEUTRAL, -0.9)

    assert result.passes is True
    assert result.confidence_boost == 0.0
