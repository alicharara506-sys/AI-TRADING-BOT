from __future__ import annotations

from core.interfaces.types import TradeSignal
from core.interfaces.validation import ValidationReport
from machine_learning.ai_assistant.llm_provider import LLMProvider
from machine_learning.ai_assistant.opinion import ConfidenceScoredOpinion, parse_opinion
from machine_learning.ai_assistant.reviewer import AIReviewer
from machine_learning.ai_assistant.rule_based_reviewer import RuleBasedReviewer

_RESPONSE_SHAPE = (
    'Respond with only JSON matching exactly this shape (no other text): '
    '{"opinion": string, "confidence": number between 0 and 1, '
    '"supporting_points": array of strings}.'
)


def _validation_report_prompt(report: ValidationReport, grounding: str) -> str:
    return (
        "You are reviewing a quantitative trading strategy's validation report "
        "for a portfolio manager. Rephrase the deterministic analysis below as a "
        "clear, professional explanation. Do not invent any fact not present in "
        f"it. {_RESPONSE_SHAPE}\n\nDeterministic analysis:\n{grounding}"
    )


def _trade_signal_prompt(signal: TradeSignal, grounding: str) -> str:
    return (
        "You are explaining a quantitative trading signal for a portfolio "
        "manager. Rephrase the deterministic analysis below as a clear, "
        "professional explanation. Do not invent any fact not present in it, "
        f"and do not recommend any action beyond explaining the signal. "
        f"{_RESPONSE_SHAPE}\n\nDeterministic analysis:\n{grounding}"
    )


def _render_opinion(opinion: ConfidenceScoredOpinion) -> str:
    lines = [f"{opinion.opinion} (LLM confidence: {opinion.confidence:.0%})"]
    lines.extend(f"- {point}" for point in opinion.supporting_points)
    return "\n".join(lines)


class LLMBackedReviewer:
    """AIReviewer implementation backed by an injected LLMProvider, with the
    deterministic RuleBasedReviewer as a mandatory fallback.

    Any failure -- the provider raising for any reason (network error, auth
    failure, rate limit, timeout), or the provider succeeding but returning
    output that fails ConfidenceScoredOpinion validation -- degrades to the
    fallback's text rather than propagating or returning malformed output.
    This generalizes the one genuinely reusable pattern found during
    research into danilobatson/ai-trading-agent-gemini (fail open to a
    deterministic result when the LLM call errors) to also cover the
    failure mode that repo didn't handle: the call *succeeding* with
    unparseable output.

    The LLM is always prompted to rephrase the RuleBasedReviewer's own
    grounded analysis, never to reason from raw evidence independently --
    the same "backed by the same numeric evidence, never an independent,
    opaque judgment" contract AIReviewer itself documents. Nothing here
    can place, modify, or cancel an order; both methods return prose.
    """

    def __init__(self, provider: LLMProvider, *, fallback: AIReviewer | None = None) -> None:
        self._provider = provider
        self._fallback = fallback or RuleBasedReviewer()

    async def review_validation_report(self, report: ValidationReport) -> str:
        fallback_text = await self._fallback.review_validation_report(report)
        prompt = _validation_report_prompt(report, fallback_text)
        return await self._generate_or_fall_back(prompt, fallback_text)

    async def explain_trade_signal(self, signal: TradeSignal) -> str:
        fallback_text = await self._fallback.explain_trade_signal(signal)
        prompt = _trade_signal_prompt(signal, fallback_text)
        return await self._generate_or_fall_back(prompt, fallback_text)

    async def _generate_or_fall_back(self, prompt: str, fallback_text: str) -> str:
        try:
            raw = await self._provider.generate(prompt)
            opinion = parse_opinion(raw)
        except Exception:  # noqa: BLE001 - any provider/parsing failure degrades to the
            # deterministic fallback by design; it must never propagate or silently
            # substitute unparsed text.
            return fallback_text
        return _render_opinion(opinion)


__all__ = ["LLMBackedReviewer"]
