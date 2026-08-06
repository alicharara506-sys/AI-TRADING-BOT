from __future__ import annotations

from datetime import timedelta

from core.interfaces.types import Direction, Evidence, MarketContext
from news_intelligence.types import AnalyzedNews


class NewsSentimentModule:
    """AnalysisModule that turns recently ingested, non-duplicate,
    sufficiently confident news into Evidence for whichever symbol they're
    relevant to -- one signal source among many in Signal Fusion, never a
    sole basis for a trade. This is the concrete proof of the Phase 7
    placement decision (docs/architecture/08-intelligence-modules.md): a
    news-derived signal is just another AnalysisModule, requiring zero
    changes to core/signal/fusion.py or core/signal/engine.py.

    News arrives out-of-band from the price/bar MarketContext analyze()
    receives, so this module holds a small buffer of recently ingested
    AnalyzedNews (fed via ingest()) rather than computing anything from
    bars itself; analyze() looks up whatever is still fresh and relevant
    for the symbol currently in play.
    """

    name = "news_sentiment"

    def __init__(
        self,
        *,
        min_confidence: float = 0.34,
        max_age: timedelta = timedelta(hours=4),
    ) -> None:
        if not (0.0 <= min_confidence <= 1.0):
            raise ValueError("min_confidence must be in [0, 1]")
        self._min_confidence = min_confidence
        self._max_age = max_age
        self._recent: list[AnalyzedNews] = []

    def ingest(self, analyzed: AnalyzedNews) -> None:
        """Duplicates are dropped here, at the boundary, so analyze() never
        has to reason about them -- the same "reject at the gate, not deep
        inside the pipeline" discipline the Validation Pipeline uses.
        """
        if analyzed.duplicate_of is not None:
            return
        self._recent.append(analyzed)

    def analyze(self, context: MarketContext) -> list[Evidence]:
        if not context.bars:
            return []
        now = context.bars[-1].timestamp
        base, quote = self._split_pair(context.symbol.canonical)

        evidence: list[Evidence] = []
        for analyzed in self._recent:
            if now - analyzed.item.published_at > self._max_age:
                continue
            if not ({base, quote} & set(analyzed.entities)):
                continue
            if analyzed.confidence < self._min_confidence or analyzed.sentiment == 0.0:
                continue

            direction = Direction.LONG if analyzed.sentiment > 0 else Direction.SHORT
            evidence.append(
                Evidence(
                    source_module=self.name,
                    direction=direction,
                    confidence=min(abs(analyzed.sentiment) * analyzed.confidence, 1.0),
                    rationale={
                        "headline": analyzed.item.headline,
                        "category": analyzed.category.value,
                        "sentiment": analyzed.sentiment,
                        "market_impact": analyzed.market_impact,
                    },
                    supporting_data={
                        "entities": analyzed.entities,
                        "source": analyzed.item.source,
                        "published_at": analyzed.item.published_at.isoformat(),
                    },
                )
            )
        return evidence

    @staticmethod
    def _split_pair(canonical_symbol: str) -> tuple[str, str]:
        if len(canonical_symbol) != 6:
            return canonical_symbol, canonical_symbol
        return canonical_symbol[:3], canonical_symbol[3:]


__all__ = ["NewsSentimentModule"]
