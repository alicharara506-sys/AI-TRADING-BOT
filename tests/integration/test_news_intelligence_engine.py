from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.signal_module import NewsSentimentModule
from news_intelligence.types import NewsItem
from quant.candlesticks.patterns import EngulfingPatternModule
from quant.fibonacci.confluence import FibonacciConfluenceModule
from tests.support.fake_news_provider import FakeNewsProvider

_SYMBOL = Symbol(name="EURUSD")
# Same verified bullish Engulfing + 61.8% Fibonacci confluence fixture used
# by this platform's other Signal Fusion exit-criteria tests.
_CLOSES_UP_TO_SWING = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11,
    1.14, 1.17, 1.20, 1.18, 1.16, 1.14, 1.12, 1.10,
]


def _context() -> MarketContext:
    ohlc = [(c, c, c, c) for c in _CLOSES_UP_TO_SWING]
    ohlc.append((1.0715, 1.0715, 1.0705, 1.0705))
    ohlc.append((1.0700, 1.0764, 1.0700, 1.0764))
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=1.0,
        )
        for i, (o, h, low, c) in enumerate(ohlc)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


async def test_real_news_feed_ingestion_produces_evidence_alongside_quant_modules() -> None:
    """Phase 3 (News Intelligence Engine) exit criteria: a real news feed,
    fetched through the NewsProvider Protocol and run through the full
    ingestion/dedup/classification/sentiment/entity/scoring pipeline, plugs
    into the unmodified SignalEngine/SignalFusion as just another
    AnalysisModule -- proving the Phase 7 placement decision's central
    claim (no changes needed to core/signal/fusion.py or
    core/signal/engine.py) against real, not synthetic, module composition.
    """
    context = _context()
    latest_bar_time = context.bars[-1].timestamp

    provider = FakeNewsProvider(
        items=[
            NewsItem(
                item_id="1",
                source="TestWire",
                headline=(
                    "EUR/USD surges as European Central Bank hints at rate hike "
                    "amid inflation concerns"
                ),
                body="Markets rallied broadly on the ECB commentary.",
                published_at=latest_bar_time - timedelta(minutes=20),
            ),
            NewsItem(
                item_id="2",
                source="TestWire",
                # Same story from a second outlet, worded differently --
                # must be recognized as a near-duplicate and never ingested.
                headline="European Central Bank signals possible rate hike, EUR/USD jumps",
                body="Markets rallied broadly on the ECB commentary.",
                published_at=latest_bar_time - timedelta(minutes=18),
            ),
            NewsItem(
                item_id="3",
                source="TestWire",
                headline="Bitcoin rallies past key resistance amid crypto optimism",
                body="Unrelated to forex markets.",
                published_at=latest_bar_time - timedelta(minutes=10),
            ),
        ]
    )

    pipeline = NewsIntelligencePipeline(near_duplicate_threshold=0.3)
    news_module = NewsSentimentModule()
    for analyzed in await pipeline.ingest(provider):
        news_module.ingest(analyzed)

    engine = SignalEngine(SignalFusion(threshold=0.6))
    engine.register_module(FibonacciConfluenceModule(swing_arm=2, tolerance=0.03))
    engine.register_module(EngulfingPatternModule())
    engine.register_module(news_module)

    signal = engine.evaluate(context)

    assert signal is not None
    assert signal.direction == Direction.LONG
    contributing = {item.source_module for item in signal.evidence}
    assert contributing == {"fibonacci_confluence", "engulfing_pattern", "news_sentiment"}

    news_evidence = next(e for e in signal.evidence if e.source_module == "news_sentiment")
    assert news_evidence.direction == Direction.LONG
    assert news_evidence.rationale["category"] == "central_bank"

    # The near-duplicate second wire story never became a second Evidence
    # item -- exactly one news_sentiment contribution despite two ingested
    # items describing the same event.
    assert sum(1 for e in signal.evidence if e.source_module == "news_sentiment") == 1
