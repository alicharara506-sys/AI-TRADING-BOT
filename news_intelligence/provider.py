from __future__ import annotations

from typing import Protocol, runtime_checkable

from news_intelligence.types import NewsItem


@runtime_checkable
class NewsProvider(Protocol):
    """Provider-agnostic interface for a news source. Reuters, Bloomberg,
    Financial Modeling Prep, Alpha Vantage, NewsAPI, Polygon, Finnhub, or
    any custom feed implements exactly this and nothing more -- fetch a
    batch of raw items, nothing else. All classification, dedup, sentiment,
    entity extraction, and scoring happen in NewsIntelligencePipeline,
    uniformly across every provider, rather than being redone (or not done
    at all) per vendor.

    Deliberately mirrors the shape of core.interfaces.execution.Connector
    and machine_learning.ai_assistant.llm_provider.LLMProvider: a thin,
    swappable boundary around one external dependency, with all real logic
    living on this platform's side of it -- the opposite of opennews-mcp's
    architecture, where the entire ingestion/classification pipeline lived
    opaquely on a single paid vendor's server.
    """

    async def fetch_latest(self, *, limit: int = 50) -> list[NewsItem]: ...


__all__ = ["NewsProvider"]
