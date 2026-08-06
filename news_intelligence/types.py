from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class NewsCategory(enum.Enum):
    CENTRAL_BANK = "central_bank"
    ECONOMIC = "economic"
    EARNINGS = "earnings"
    REGULATORY = "regulatory"
    COMPANY = "company"
    COMMODITY = "commodity"
    CRYPTO = "crypto"
    FOREX = "forex"
    GENERAL_MARKET = "general_market"


@dataclass(frozen=True, slots=True)
class NewsItem:
    """A raw news item exactly as received from a NewsProvider, before any
    analysis. Provider-agnostic -- Reuters, Bloomberg, NewsAPI, a custom
    feed, or the fixed test double all produce this same shape.
    """

    item_id: str
    source: str
    headline: str
    body: str
    published_at: datetime
    url: str = ""


@dataclass(frozen=True, slots=True)
class AnalyzedNews:
    """The News Intelligence Engine's output for one item. Every score
    carries the evidence that produced it (matched terms, extracted
    entities) rather than being an opaque number -- the same
    "explainable, not just confident" discipline Evidence/SignalFusion
    already enforces elsewhere in the platform.
    """

    item: NewsItem
    category: NewsCategory
    category_confidence: float
    language: str
    sentiment: float
    sentiment_matched_terms: tuple[str, ...]
    entities: tuple[str, ...]
    relevance: float
    confidence: float
    market_impact: float
    duplicate_of: str | None = None


__all__ = ["AnalyzedNews", "NewsCategory", "NewsItem"]
