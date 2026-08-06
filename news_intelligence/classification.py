from __future__ import annotations

from news_intelligence.types import NewsCategory

_CATEGORY_KEYWORDS: dict[NewsCategory, tuple[str, ...]] = {
    NewsCategory.CENTRAL_BANK: (
        "federal reserve", "fomc", "european central bank", "ecb",
        "bank of england", "bank of japan", "people's bank of china",
        "interest rate decision", "rate hike", "rate cut", "monetary policy",
    ),
    NewsCategory.ECONOMIC: (
        "gdp", "inflation", "cpi", "unemployment rate", "nonfarm payroll",
        "retail sales", "pmi", "consumer confidence",
    ),
    NewsCategory.EARNINGS: (
        "quarterly earnings", "quarterly results", "earnings per share",
        "revenue beat", "revenue miss", "guidance raised", "guidance cut",
    ),
    NewsCategory.REGULATORY: (
        "sec charges", "regulator", "antitrust", "compliance violation",
        "sanctions", "regulatory approval", "lawsuit filed",
    ),
    NewsCategory.COMMODITY: (
        "crude oil", "gold price", "opec", "natural gas", "commodity prices",
    ),
    NewsCategory.CRYPTO: (
        "bitcoin", "ethereum", "cryptocurrency", "blockchain", "stablecoin",
    ),
    NewsCategory.FOREX: (
        "currency pair", "forex market", "exchange rate", "eur/usd", "usd/jpy",
        "gbp/usd", "currency intervention",
    ),
    NewsCategory.COMPANY: (
        "acquisition", "merger agreement", "chief executive", "product launch",
        "initial public offering",
    ),
}


def classify(text: str) -> tuple[NewsCategory, float]:
    """Rule-based keyword-taxonomy classifier: counts keyword hits per
    category, picks the highest, and reports confidence as that category's
    share of all keyword hits across every category -- 1.0 when only one
    category matched at all, lower when several compete for the same
    headline. Returns GENERAL_MARKET with confidence 0.0 when nothing
    matches, an honest "we don't know" rather than a forced guess.
    """
    lowered = text.lower()
    hits = {
        category: sum(1 for keyword in keywords if keyword in lowered)
        for category, keywords in _CATEGORY_KEYWORDS.items()
    }
    total_hits = sum(hits.values())
    if total_hits == 0:
        return NewsCategory.GENERAL_MARKET, 0.0

    best_category = max(hits, key=lambda category: hits[category])
    confidence = hits[best_category] / total_hits
    return best_category, confidence


__all__ = ["classify"]
