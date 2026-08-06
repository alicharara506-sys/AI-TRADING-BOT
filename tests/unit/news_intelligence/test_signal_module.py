from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.signal_module import NewsSentimentModule
from news_intelligence.types import NewsItem

_SYMBOL = Symbol(name="EURUSD")
_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _context() -> MarketContext:
    bar = Bar(
        symbol=_SYMBOL, timeframe=Timeframe.M1, timestamp=_NOW,
        open=1.1, high=1.1, low=1.1, close=1.1, volume=0.0,
    )
    return MarketContext(symbol=_SYMBOL, bars=(bar,))


def _analyzed_item(headline: str, published_at: datetime, item_id: str = "1"):
    pipeline = NewsIntelligencePipeline()
    item = NewsItem(
        item_id=item_id, source="wire", headline=headline, body="",
        published_at=published_at,
    )
    return pipeline.analyze(item)


def test_relevant_positive_news_produces_long_evidence() -> None:
    module = NewsSentimentModule()
    analyzed = _analyzed_item(
        "EUR/USD surges as European Central Bank hints at rate hike amid inflation concerns",
        _NOW - timedelta(minutes=30),
    )
    module.ingest(analyzed)

    evidence = module.analyze(_context())

    assert len(evidence) == 1
    assert evidence[0].source_module == "news_sentiment"
    assert evidence[0].direction == Direction.LONG
    expected_confidence = min(abs(analyzed.sentiment) * analyzed.confidence, 1.0)
    assert evidence[0].confidence == pytest.approx(expected_confidence)
    assert evidence[0].rationale["category"] == "central_bank"


def test_negative_news_produces_short_evidence() -> None:
    module = NewsSentimentModule()
    analyzed = _analyzed_item(
        "EUR crashes as European Central Bank signals recession and downgrade",
        _NOW - timedelta(minutes=30),
    )
    module.ingest(analyzed)

    evidence = module.analyze(_context())

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT


def test_irrelevant_symbol_produces_no_evidence() -> None:
    module = NewsSentimentModule()
    analyzed = _analyzed_item(
        "Bitcoin rallies past key resistance amid crypto market optimism",
        _NOW - timedelta(minutes=30),
    )
    module.ingest(analyzed)

    evidence = module.analyze(_context())

    assert evidence == []


def test_stale_news_beyond_max_age_produces_no_evidence() -> None:
    module = NewsSentimentModule(max_age=timedelta(minutes=5))
    analyzed = _analyzed_item(
        "EUR/USD surges as European Central Bank hints at rate hike",
        _NOW - timedelta(hours=2),
    )
    module.ingest(analyzed)

    evidence = module.analyze(_context())

    assert evidence == []


def test_neutral_sentiment_news_produces_no_evidence() -> None:
    module = NewsSentimentModule()
    analyzed = _analyzed_item(
        "European Central Bank holds meeting on EUR policy",
        _NOW - timedelta(minutes=30),
    )
    module.ingest(analyzed)

    evidence = module.analyze(_context())

    assert evidence == []


def test_duplicate_news_is_never_ingested() -> None:
    module = NewsSentimentModule()
    pipeline = NewsIntelligencePipeline()
    headline = "EUR/USD surges as European Central Bank hints at rate hike amid inflation concerns"
    first = pipeline.analyze(
        NewsItem(item_id="1", source="A", headline=headline, body="", published_at=_NOW)
    )
    duplicate = pipeline.analyze(
        NewsItem(item_id="2", source="B", headline=headline, body="", published_at=_NOW)
    )
    assert duplicate.duplicate_of == "1"

    module.ingest(first)
    module.ingest(duplicate)

    evidence = module.analyze(_context())
    assert len(evidence) == 1  # not double-counted


def test_low_confidence_news_below_threshold_produces_no_evidence() -> None:
    module = NewsSentimentModule(min_confidence=0.99)
    analyzed = _analyzed_item(
        "EUR/USD surges as European Central Bank hints at rate hike amid inflation concerns",
        _NOW - timedelta(minutes=30),
    )
    module.ingest(analyzed)

    evidence = module.analyze(_context())

    assert evidence == []


def test_empty_context_bars_produces_no_evidence() -> None:
    module = NewsSentimentModule()
    context = MarketContext(symbol=_SYMBOL, bars=())

    assert module.analyze(context) == []


def test_rejects_invalid_min_confidence() -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        NewsSentimentModule(min_confidence=1.5)
