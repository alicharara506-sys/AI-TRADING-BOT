from __future__ import annotations

from news_intelligence.entities import extract_entities


def test_extracts_currency_codes() -> None:
    entities = extract_entities("EUR/USD volatile as GBP weakens")

    assert set(entities) >= {"EUR", "USD", "GBP"}


def test_extracts_central_banks() -> None:
    entities = extract_entities("The Federal Reserve and European Central Bank both spoke today")

    assert "FED" in entities
    assert "ECB" in entities


def test_extracts_commodities() -> None:
    entities = extract_entities("Gold and crude oil prices moved sharply")

    assert "XAU" in entities
    assert "OIL" in entities


def test_lowercase_currency_mentions_are_not_matched_case_insensitively() -> None:
    """Entity extraction is intentionally case-sensitive for currency
    codes: 'eur' lowercase in running prose is far more likely to be part
    of an unrelated word than an actual currency reference, unlike 'EUR'
    which conventionally only appears as the code itself.
    """
    entities = extract_entities("the amateur eur usd talk was just chatter")

    assert entities == ()


def test_no_entities_returns_empty_tuple() -> None:
    assert extract_entities("A quiet day with nothing notable") == ()


def test_result_is_sorted_and_deduplicated() -> None:
    entities = extract_entities("USD USD USD and EUR")

    assert entities == ("EUR", "USD")
