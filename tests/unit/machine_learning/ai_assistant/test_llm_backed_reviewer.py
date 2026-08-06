from __future__ import annotations

from core.interfaces.validation import CheckResult, ValidationReport
from machine_learning.ai_assistant.llm_backed_reviewer import LLMBackedReviewer
from machine_learning.ai_assistant.rule_based_reviewer import RuleBasedReviewer
from tests.support.fake_llm_provider import FakeLLMProvider

_REPORT = ValidationReport(
    strategy_name="steady_strategy",
    checks=(
        CheckResult(
            name="walk_forward", passed=True, detail={"degradation": 0.1, "max_degradation": 0.5}
        ),
    ),
)


async def test_valid_llm_response_is_rendered_with_confidence_and_points() -> None:
    provider = FakeLLMProvider(
        next_response=(
            '{"opinion": "Strategy looks robust based on walk-forward stability.", '
            '"confidence": 0.92, "supporting_points": ["low degradation", "consistent returns"]}'
        )
    )
    reviewer = LLMBackedReviewer(provider)

    text = await reviewer.review_validation_report(_REPORT)

    assert "Strategy looks robust based on walk-forward stability." in text
    assert "92%" in text
    assert "- low degradation" in text
    assert "- consistent returns" in text


async def test_prompt_grounds_the_llm_in_the_rule_based_analysis() -> None:
    provider = FakeLLMProvider(
        next_response='{"opinion": "ok", "confidence": 0.5, "supporting_points": []}'
    )
    reviewer = LLMBackedReviewer(provider)

    await reviewer.review_validation_report(_REPORT)

    assert len(provider.prompts_received) == 1
    assert "walk_forward" in provider.prompts_received[0]
    assert "PASSED" in provider.prompts_received[0]


async def test_provider_failure_falls_back_to_rule_based_reviewer_exactly() -> None:
    provider = FakeLLMProvider(error=RuntimeError("network down"))
    reviewer = LLMBackedReviewer(provider)

    text = await reviewer.review_validation_report(_REPORT)
    expected = await RuleBasedReviewer().review_validation_report(_REPORT)

    assert text == expected


async def test_malformed_llm_output_falls_back_to_rule_based_reviewer_exactly() -> None:
    provider = FakeLLMProvider(next_response="this is not JSON")
    reviewer = LLMBackedReviewer(provider)

    text = await reviewer.review_validation_report(_REPORT)
    expected = await RuleBasedReviewer().review_validation_report(_REPORT)

    assert text == expected


async def test_out_of_range_confidence_falls_back_rather_than_silently_clamping() -> None:
    """Direct regression guard against the exact anti-pattern found in
    ai-trading-agent-gemini: an out-of-range confidence must not be
    silently clamped into something plausible -- it must be treated as a
    malformed response and trigger the fallback.
    """
    provider = FakeLLMProvider(
        next_response='{"opinion": "overconfident", "confidence": 5.0, "supporting_points": []}'
    )
    reviewer = LLMBackedReviewer(provider)

    text = await reviewer.review_validation_report(_REPORT)
    expected = await RuleBasedReviewer().review_validation_report(_REPORT)

    assert text == expected
    assert "overconfident" not in text


async def test_custom_fallback_is_used_instead_of_the_default() -> None:
    class _StubFallback:
        async def review_validation_report(self, report: ValidationReport) -> str:
            return "stub fallback text"

        async def explain_trade_signal(self, signal: object) -> str:  # pragma: no cover
            raise NotImplementedError

    provider = FakeLLMProvider(error=RuntimeError("down"))
    reviewer = LLMBackedReviewer(provider, fallback=_StubFallback())

    text = await reviewer.review_validation_report(_REPORT)

    assert text == "stub fallback text"
