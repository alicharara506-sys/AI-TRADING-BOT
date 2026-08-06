from __future__ import annotations

from datetime import UTC, datetime

import pytest

from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.types import NewsCategory, NewsItem
from tests.support.fake_news_provider import FakeNewsProvider


def _item(item_id: str, headline: str, body: str = "") -> NewsItem:
    return NewsItem(
        item_id=item_id, source="wire", headline=headline, body=body,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_analyze_wires_every_stage_together() -> None:
    pipeline = NewsIntelligencePipeline()
    item = _item(
        "1",
        "EUR/USD surges as European Central Bank hints at rate hike amid inflation concerns",
        "Markets rallied on the news.",
    )

    analyzed = pipeline.analyze(item)

    assert analyzed.item is item
    assert analyzed.category == NewsCategory.CENTRAL_BANK
    assert analyzed.sentiment > 0.0
    assert set(analyzed.entities) >= {"ECB", "EUR", "USD"}
    assert analyzed.relevance == pytest.approx(1.0)
    assert analyzed.confidence > 0.0
    assert analyzed.market_impact > 0.0
    assert analyzed.duplicate_of is None


def test_pipeline_deduplicates_across_analyze_calls() -> None:
    pipeline = NewsIntelligencePipeline()
    first = pipeline.analyze(_item("1", "Fed holds rates steady", "No policy change"))
    second = pipeline.analyze(_item("2", "Fed holds rates steady", "No policy change"))

    assert first.duplicate_of is None
    assert second.duplicate_of == "1"


async def test_ingest_fetches_from_provider_and_analyzes_every_item() -> None:
    pipeline = NewsIntelligencePipeline()
    provider = FakeNewsProvider(
        items=[
            _item("1", "Federal Reserve holds interest rates steady"),
            _item("2", "Bitcoin rallies past key resistance level"),
        ]
    )

    results = await pipeline.ingest(provider)

    assert len(results) == 2
    assert results[0].category == NewsCategory.CENTRAL_BANK
    assert results[1].category == NewsCategory.CRYPTO


async def test_ingest_respects_the_limit() -> None:
    pipeline = NewsIntelligencePipeline()
    provider = FakeNewsProvider(items=[_item(str(i), f"Headline {i}") for i in range(10)])

    results = await pipeline.ingest(provider, limit=3)

    assert len(results) == 3


def test_custom_tracked_symbols_change_relevance_scoring() -> None:
    pipeline = NewsIntelligencePipeline(tracked_symbols={"XAU"})
    item = _item("1", "EUR/USD surges on central bank rate hike speculation")

    analyzed = pipeline.analyze(item)

    # EUR/USD is extracted as entities but not in the (narrowed) tracked set.
    assert analyzed.relevance == pytest.approx(0.0)
