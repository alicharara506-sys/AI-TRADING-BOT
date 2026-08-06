from __future__ import annotations

from collections.abc import Collection

from news_intelligence.types import NewsCategory

_CATEGORY_IMPACT_WEIGHT: dict[NewsCategory, float] = {
    NewsCategory.CENTRAL_BANK: 1.0,
    NewsCategory.ECONOMIC: 0.8,
    NewsCategory.FOREX: 0.7,
    NewsCategory.EARNINGS: 0.6,
    NewsCategory.REGULATORY: 0.6,
    NewsCategory.COMMODITY: 0.6,
    NewsCategory.CRYPTO: 0.5,
    NewsCategory.COMPANY: 0.4,
    NewsCategory.GENERAL_MARKET: 0.2,
}


def score_relevance(entities: Collection[str], tracked_symbols: Collection[str]) -> float:
    """Fraction of extracted entities that the platform actually tracks.
    0.0 when nothing was extracted at all -- no entities means no basis to
    claim relevance to anything specific, not a default middling score.
    """
    if not entities:
        return 0.0
    tracked = frozenset(tracked_symbols)
    matched = sum(1 for entity in entities if entity in tracked)
    return matched / len(entities)


def score_confidence(
    *, category_confidence: float, entity_count: int, sentiment_term_count: int
) -> float:
    """How much signal this analysis actually has to stand on: category
    confidence averaged with two simple presence bonuses (were any entities
    found, were any sentiment terms found). Deliberately simple and
    auditable -- three numbers averaged -- rather than a black-box
    combination nobody could explain to an operator.
    """
    entity_signal = 1.0 if entity_count > 0 else 0.0
    sentiment_signal = 1.0 if sentiment_term_count > 0 else 0.0
    return (category_confidence + entity_signal + sentiment_signal) / 3.0


def score_market_impact(*, category: NewsCategory, relevance: float, sentiment: float) -> float:
    """Deterministic, explainable estimate in [0, 1] of how much this item
    plausibly moves markets it's relevant to: category severity times
    relevance times a sentiment-strength multiplier that never zeroes out
    a high-severity category just because the lexicon found no explicit
    positive/negative words (e.g. "Fed holds rates steady" is still
    central-bank news even with neutral wording) -- the multiplier ranges
    [0.5, 1.0], not [0.0, 1.0].
    """
    weight = _CATEGORY_IMPACT_WEIGHT[category]
    sentiment_multiplier = 0.5 + 0.5 * abs(sentiment)
    return weight * relevance * sentiment_multiplier


__all__ = ["score_confidence", "score_market_impact", "score_relevance"]
