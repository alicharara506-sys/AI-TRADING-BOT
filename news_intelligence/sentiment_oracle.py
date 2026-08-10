from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from core.interfaces.types import Direction
from machine_learning.ai_assistant.llm_provider import LLMProvider
from machine_learning.ai_assistant.ollama_llm_provider import OllamaLLMProvider
from news_intelligence.types import NewsItem

_DEFAULT_OLLAMA_PORTS: tuple[int, ...] = (11434, 11435, 11436, 11437)
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

_SENTIMENT_PROMPT_TEMPLATE = (
    "Rate market sentiment for {symbol} from -1 (bearish) to +1 (bullish) "
    "based on the following recent headlines. Respond ONLY with a number.\n\n"
    "{headlines}"
)


def _parse_sentiment_response(raw: str) -> float | None:
    """Extracts the first number in `raw` and clamps it to [-1, 1] -- an
    LLM asked to "respond ONLY with a number" will still occasionally wrap
    it in a sentence or extra punctuation, so this deliberately doesn't
    require an exact float() parse of the whole string. None (excluded
    from the consensus average, never treated as 0.0) when no number is
    found at all."""
    match = _NUMBER_PATTERN.search(raw)
    if match is None:
        return None
    return max(-1.0, min(1.0, float(match.group())))


class LocalLLMConsensusEngine:
    """Fans a market-sentiment prompt out to every configured local LLM in
    parallel (four Ollama models on ports 11434-11437 by default -- free,
    offline, no API key, the exact deployment this platform's four local
    models already run under) and averages the parseable responses.

    Any model that fails -- connection refused, timeout, malformed/
    unparseable output -- is excluded from the average rather than treated
    as a 0.0/neutral vote, the same "exclude the unusable, don't fabricate
    a value for it" principle FredMacroProvider already applies to a
    missing observation (macro_data/providers/fred.py). Returns None only
    when every single model failed to produce a usable number -- there is
    no consensus to report, not a fabricated neutral one.
    """

    def __init__(self, providers: Sequence[LLMProvider]) -> None:
        if not providers:
            raise ValueError("providers must not be empty")
        self._providers = list(providers)

    @classmethod
    def with_default_ollama_ports(
        cls, *, model: str = "llama3", ports: Sequence[int] = _DEFAULT_OLLAMA_PORTS
    ) -> LocalLLMConsensusEngine:
        providers: list[LLMProvider] = [
            OllamaLLMProvider(base_url=f"http://localhost:{port}", model=model) for port in ports
        ]
        return cls(providers)

    async def consensus_sentiment(self, symbol: str, headlines: Sequence[NewsItem]) -> float | None:
        headline_text = "\n".join(f"- {item.headline}" for item in headlines)
        prompt = _SENTIMENT_PROMPT_TEMPLATE.format(
            symbol=symbol, headlines=headline_text or "(no recent headlines)"
        )
        raw_responses = await asyncio.gather(
            *(provider.generate(prompt) for provider in self._providers), return_exceptions=True
        )

        values: list[float] = []
        for raw in raw_responses:
            if isinstance(raw, BaseException):
                continue
            parsed = _parse_sentiment_response(raw)
            if parsed is not None:
                values.append(parsed)

        if not values:
            return None
        return sum(values) / len(values)


@dataclass(frozen=True, slots=True)
class SentimentSample:
    value: float
    at: datetime


class SentimentSpikeDetector:
    """Rolling-window z-score spike detector: a spike is flagged when the
    most recently recorded sentiment reading is more than `zscore_threshold`
    standard deviations from the mean of the same rolling window (24h by
    default) it's compared against. Pure arithmetic over an in-memory
    sample buffer -- no persistence, symmetric to the momentary,
    process-lifetime nature of a live sentiment feed.
    """

    def __init__(
        self, *, window: timedelta = timedelta(hours=24), zscore_threshold: float = 2.0
    ) -> None:
        if zscore_threshold <= 0:
            raise ValueError("zscore_threshold must be > 0")
        self._window = window
        self._zscore_threshold = zscore_threshold
        self._samples: list[SentimentSample] = []

    def record(self, value: float, *, at: datetime) -> None:
        self._samples.append(SentimentSample(value=value, at=at))
        cutoff = at - self._window
        self._samples = [sample for sample in self._samples if sample.at >= cutoff]

    def latest_zscore(self) -> float | None:
        if len(self._samples) < 2:
            return None
        values = [sample.value for sample in self._samples]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        std = variance**0.5
        if std < 1e-12:
            return 0.0
        return float((values[-1] - mean) / std)

    def is_spike(self) -> bool:
        zscore = self.latest_zscore()
        return zscore is not None and abs(zscore) >= self._zscore_threshold


@dataclass(frozen=True, slots=True)
class SentimentGateResult:
    passes: bool
    confidence_boost: float
    reason: str


class SentimentConfirmationFilter:
    """Sentiment as a confirmation filter only, never a direction generator
    -- the same "LLM text does not decide trade direction" principle
    already established for this platform's LLMBackedReviewer (which only
    ever rephrases a deterministic analysis, never reasons independently).

    A LONG signal requires consensus sentiment no more bearish than
    `long_floor`; a SHORT signal requires no more bullish than
    `short_ceiling`. A sentiment spike (|z-score| past
    SentimentSpikeDetector's own threshold) *aligned* with the signal's
    direction adds `spike_confidence_boost` to confidence; a spike
    *opposing* the signal's direction blocks it outright, evaluated before
    the floor/ceiling check so an opposing spike can't be waved through by
    an otherwise-passing raw sentiment score.
    """

    def __init__(
        self,
        *,
        long_floor: float = -0.2,
        short_ceiling: float = 0.2,
        spike_threshold: float = 0.7,
        spike_confidence_boost: float = 0.05,
    ) -> None:
        if not -1.0 <= long_floor <= 1.0:
            raise ValueError("long_floor must be in [-1, 1]")
        if not -1.0 <= short_ceiling <= 1.0:
            raise ValueError("short_ceiling must be in [-1, 1]")
        if not 0.0 <= spike_threshold <= 1.0:
            raise ValueError("spike_threshold must be in [0, 1]")
        self._long_floor = long_floor
        self._short_ceiling = short_ceiling
        self._spike_threshold = spike_threshold
        self._spike_confidence_boost = spike_confidence_boost

    def evaluate(self, direction: Direction, sentiment: float) -> SentimentGateResult:
        if direction is Direction.LONG:
            return self._evaluate_long(sentiment)
        if direction is Direction.SHORT:
            return self._evaluate_short(sentiment)
        return SentimentGateResult(True, 0.0, "neutral direction: sentiment gate does not apply")

    def _evaluate_long(self, sentiment: float) -> SentimentGateResult:
        if sentiment <= -self._spike_threshold:
            return SentimentGateResult(
                False, 0.0, f"opposing bearish sentiment spike ({sentiment:.2f})"
            )
        if sentiment < self._long_floor:
            return SentimentGateResult(
                False, 0.0, f"sentiment {sentiment:.2f} below LONG floor {self._long_floor:.2f}"
            )
        if sentiment >= self._spike_threshold:
            reason = f"aligned bullish sentiment spike ({sentiment:.2f})"
            return SentimentGateResult(True, self._spike_confidence_boost, reason)
        return SentimentGateResult(True, 0.0, f"sentiment {sentiment:.2f} confirms LONG")

    def _evaluate_short(self, sentiment: float) -> SentimentGateResult:
        if sentiment >= self._spike_threshold:
            return SentimentGateResult(
                False, 0.0, f"opposing bullish sentiment spike ({sentiment:.2f})"
            )
        if sentiment > self._short_ceiling:
            reason = f"sentiment {sentiment:.2f} above SHORT ceiling {self._short_ceiling:.2f}"
            return SentimentGateResult(False, 0.0, reason)
        if sentiment <= -self._spike_threshold:
            reason = f"aligned bearish sentiment spike ({sentiment:.2f})"
            return SentimentGateResult(True, self._spike_confidence_boost, reason)
        return SentimentGateResult(True, 0.0, f"sentiment {sentiment:.2f} confirms SHORT")


__all__ = [
    "LocalLLMConsensusEngine",
    "SentimentConfirmationFilter",
    "SentimentGateResult",
    "SentimentSample",
    "SentimentSpikeDetector",
]
