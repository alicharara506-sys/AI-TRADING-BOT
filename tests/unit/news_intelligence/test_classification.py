from __future__ import annotations

import pytest

from news_intelligence.classification import classify
from news_intelligence.types import NewsCategory


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Federal Reserve holds interest rates steady, signals no rate cut",
            NewsCategory.CENTRAL_BANK,
        ),
        (
            "US inflation CPI data comes in hotter than expected, GDP revised",
            NewsCategory.ECONOMIC,
        ),
        (
            "Apple reports record quarterly earnings, beats revenue estimates",
            NewsCategory.EARNINGS,
        ),
        (
            "SEC charges executive with fraud, regulator opens investigation",
            NewsCategory.REGULATORY,
        ),
        ("Crude oil prices rise as OPEC agrees to cut production", NewsCategory.COMMODITY),
        ("Bitcoin and Ethereum rally as blockchain adoption grows", NewsCategory.CRYPTO),
        ("EUR/USD currency pair volatile ahead of exchange rate decision", NewsCategory.FOREX),
        ("Company announces acquisition and merger agreement with rival", NewsCategory.COMPANY),
    ],
)
def test_classifies_into_the_expected_category(text: str, expected: NewsCategory) -> None:
    category, confidence = classify(text)

    assert category == expected
    assert confidence > 0.0


def test_no_keyword_match_returns_general_market_with_zero_confidence() -> None:
    category, confidence = classify("A quiet day with nothing of note happening anywhere")

    assert category == NewsCategory.GENERAL_MARKET
    assert confidence == 0.0


def test_confidence_is_one_when_only_one_category_matches() -> None:
    _, confidence = classify("Federal Reserve holds interest rates steady")

    assert confidence == pytest.approx(1.0)


def test_confidence_is_diluted_when_multiple_categories_compete() -> None:
    # Both central_bank and forex keywords present.
    _, confidence = classify(
        "Federal Reserve rate hike triggers currency pair volatility in forex market"
    )

    assert 0.0 < confidence < 1.0
