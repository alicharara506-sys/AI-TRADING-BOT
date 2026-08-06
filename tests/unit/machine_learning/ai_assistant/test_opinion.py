from __future__ import annotations

import pydantic
import pytest

from machine_learning.ai_assistant.opinion import parse_opinion


def test_parses_valid_json() -> None:
    opinion = parse_opinion(
        '{"opinion": "looks fine", "confidence": 0.8, "supporting_points": ["a", "b"]}'
    )

    assert opinion.opinion == "looks fine"
    assert opinion.confidence == pytest.approx(0.8)
    assert opinion.supporting_points == ["a", "b"]


def test_supporting_points_defaults_to_empty_list() -> None:
    opinion = parse_opinion('{"opinion": "x", "confidence": 0.5}')

    assert opinion.supporting_points == []


@pytest.mark.parametrize(
    "raw_text",
    [
        "not json at all",
        '{"opinion": "x"}',  # missing confidence
        '{"opinion": "x", "confidence": 5.0}',  # out of [0, 1]
        '{"opinion": "x", "confidence": -0.1}',
        '{"opinion": "", "confidence": 0.5}',  # empty opinion
    ],
)
def test_rejects_malformed_or_out_of_range_output(raw_text: str) -> None:
    """The direct fix for ai-trading-agent-gemini's silent-default anti-pattern:
    malformed output raises, it is never coerced into a plausible-looking
    substitute value.
    """
    with pytest.raises(pydantic.ValidationError):
        parse_opinion(raw_text)
