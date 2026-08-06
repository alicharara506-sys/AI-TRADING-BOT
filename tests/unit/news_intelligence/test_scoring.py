from __future__ import annotations

import pytest

from news_intelligence.scoring import score_confidence, score_market_impact, score_relevance
from news_intelligence.types import NewsCategory


def test_relevance_is_zero_with_no_entities() -> None:
    assert score_relevance((), {"EUR", "USD"}) == 0.0


def test_relevance_is_fraction_of_entities_that_are_tracked() -> None:
    assert score_relevance(("EUR", "GBP"), {"EUR"}) == pytest.approx(0.5)
    assert score_relevance(("EUR", "USD"), {"EUR", "USD"}) == pytest.approx(1.0)
    assert score_relevance(("XAU",), {"EUR", "USD"}) == pytest.approx(0.0)


def test_confidence_averages_category_confidence_with_presence_bonuses() -> None:
    # category_confidence=1.0, entities found, sentiment terms found -> all 1.0
    assert score_confidence(
        category_confidence=1.0, entity_count=2, sentiment_term_count=1
    ) == pytest.approx(1.0)
    # nothing found at all -> 0.0
    assert score_confidence(
        category_confidence=0.0, entity_count=0, sentiment_term_count=0
    ) == pytest.approx(0.0)
    # only category confidence -> averaged with two zero bonuses
    assert score_confidence(
        category_confidence=0.6, entity_count=0, sentiment_term_count=0
    ) == pytest.approx(0.2)


def test_market_impact_is_bounded_by_category_weight() -> None:
    impact = score_market_impact(
        category=NewsCategory.CENTRAL_BANK, relevance=1.0, sentiment=1.0
    )
    assert impact == pytest.approx(1.0)  # weight 1.0 * relevance 1.0 * multiplier 1.0


def test_market_impact_is_nonzero_even_with_neutral_sentiment() -> None:
    """A high-severity category with neutral wording ('Fed holds rates
    steady') still carries real market impact -- the sentiment multiplier
    only ranges [0.5, 1.0], it never zeroes out the category weight.
    """
    impact = score_market_impact(category=NewsCategory.CENTRAL_BANK, relevance=1.0, sentiment=0.0)

    assert impact == pytest.approx(0.5)


def test_market_impact_is_zero_with_zero_relevance() -> None:
    impact = score_market_impact(category=NewsCategory.CENTRAL_BANK, relevance=0.0, sentiment=1.0)

    assert impact == 0.0


def test_low_severity_category_produces_lower_impact_than_high_severity() -> None:
    high = score_market_impact(category=NewsCategory.CENTRAL_BANK, relevance=1.0, sentiment=1.0)
    low = score_market_impact(category=NewsCategory.GENERAL_MARKET, relevance=1.0, sentiment=1.0)

    assert high > low
