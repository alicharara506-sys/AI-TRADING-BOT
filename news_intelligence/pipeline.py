from __future__ import annotations

from collections.abc import Collection

from news_intelligence.classification import classify
from news_intelligence.dedup import Deduplicator
from news_intelligence.entities import extract_entities
from news_intelligence.language import detect_language
from news_intelligence.provider import NewsProvider
from news_intelligence.scoring import score_confidence, score_market_impact, score_relevance
from news_intelligence.sentiment import score_sentiment
from news_intelligence.types import AnalyzedNews, NewsItem

_DEFAULT_TRACKED_SYMBOLS = frozenset({
    "EUR", "USD", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF",
    "FED", "ECB", "BOE", "BOJ",
})


class NewsIntelligencePipeline:
    """Ingestion -> dedup -> classification -> language -> sentiment ->
    entity extraction -> scoring, uniformly applied to every NewsItem
    regardless of which NewsProvider it came from. This is the platform's
    own logic, unlike opennews-mcp, where the equivalent pipeline lives
    opaquely on a single paid vendor's server and this codebase would have
    had no visibility into (or control over) how it actually works.

    Known limitation, disclosed rather than hidden: the lexicon-based
    sentiment scorer has no entity attribution -- "gold prices plunge as
    the dollar strengthens" matches both a negative term (plunge) and a
    positive term (strong) and nets to neutral, even though the two terms
    describe different instruments moving in opposite directions. This is
    the well-understood limitation of bag-of-words sentiment; NewsSentimentModule
    treats it as one Evidence source among many specifically so no single
    module's blind spot can drive a trade alone.
    """

    def __init__(
        self,
        *,
        tracked_symbols: Collection[str] | None = None,
        near_duplicate_threshold: float = 0.75,
    ) -> None:
        self._tracked_symbols = frozenset(tracked_symbols or _DEFAULT_TRACKED_SYMBOLS)
        self._dedup = Deduplicator(near_duplicate_threshold=near_duplicate_threshold)

    def analyze(self, item: NewsItem) -> AnalyzedNews:
        text = f"{item.headline} {item.body}"

        duplicate_of = self._dedup.check(item)
        category, category_confidence = classify(text)
        language = detect_language(text)
        sentiment, sentiment_terms = score_sentiment(text)
        entities = extract_entities(text)
        relevance = score_relevance(entities, self._tracked_symbols)
        confidence = score_confidence(
            category_confidence=category_confidence,
            entity_count=len(entities),
            sentiment_term_count=len(sentiment_terms),
        )
        market_impact = score_market_impact(
            category=category, relevance=relevance, sentiment=sentiment
        )

        return AnalyzedNews(
            item=item,
            category=category,
            category_confidence=category_confidence,
            language=language,
            sentiment=sentiment,
            sentiment_matched_terms=sentiment_terms,
            entities=entities,
            relevance=relevance,
            confidence=confidence,
            market_impact=market_impact,
            duplicate_of=duplicate_of,
        )

    async def ingest(self, provider: NewsProvider, *, limit: int = 50) -> list[AnalyzedNews]:
        items = await provider.fetch_latest(limit=limit)
        return [self.analyze(item) for item in items]


__all__ = ["NewsIntelligencePipeline"]
