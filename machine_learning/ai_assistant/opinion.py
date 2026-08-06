from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceScoredOpinion(BaseModel):
    """The one structured shape every LLM-backed advisory call in this
    platform must produce.

    Fixes a specific failure mode found during research into
    danilobatson/ai-trading-agent-gemini: that repo extracted SIGNAL/
    CONFIDENCE/REASONING fields from free-text model output with bare
    regexes, silently substituting a plausible-looking default (confidence
    50, signal HOLD) whenever a field failed to match -- which hides a
    malformed model response instead of surfacing it. Pydantic validation
    here raises on malformed input instead; the caller decides what to do
    about that (LLMBackedReviewer falls back to the deterministic
    RuleBasedReviewer), but it is a visible decision, not a silent
    substitution.
    """

    model_config = ConfigDict(frozen=True)

    opinion: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_points: list[str] = Field(default_factory=list)


def parse_opinion(raw_text: str) -> ConfidenceScoredOpinion:
    """Raises pydantic.ValidationError on anything that isn't valid JSON
    matching the schema -- deliberately, so a malformed LLM response is
    caught by the caller rather than silently coerced into something
    plausible-looking.
    """
    return ConfidenceScoredOpinion.model_validate_json(raw_text)


__all__ = ["ConfidenceScoredOpinion", "parse_opinion"]
