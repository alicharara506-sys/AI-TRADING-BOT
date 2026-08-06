from __future__ import annotations

# A financial-news-specific bag-of-words lexicon, not a general-purpose
# sentiment dictionary -- the same trade-off RuleBasedReviewer makes
# elsewhere: an honest, auditable baseline (every score traces to specific
# matched terms) rather than an opaque model with no explanation.
_POSITIVE_TERMS = frozenset({
    "surge", "surged", "surges", "beat", "beats", "beating", "growth", "rally",
    "rallied", "gain", "gains", "record high", "outperform", "outperformed",
    "upgrade", "upgraded", "bullish", "strong", "expansion", "recovery",
    "rebound", "rebounded", "soar", "soared",
})
_NEGATIVE_TERMS = frozenset({
    "plunge", "plunged", "plunges", "miss", "misses", "missed", "recession",
    "slump", "slumped", "crash", "crashed", "decline", "declined",
    "downgrade", "downgraded", "bearish", "weak", "weakness", "contraction",
    "default", "layoffs", "sell-off", "selloff", "tumble", "tumbled",
})


def score_sentiment(text: str) -> tuple[float, tuple[str, ...]]:
    """Bag-of-words lexicon sentiment in [-1, 1]:
    (positive_hits - negative_hits) / total_hits. Returns (0.0, ()) --
    neutral by absence of evidence, not a guess -- when no lexicon term
    appears at all.
    """
    lowered = text.lower()
    positive_matches = tuple(term for term in _POSITIVE_TERMS if term in lowered)
    negative_matches = tuple(term for term in _NEGATIVE_TERMS if term in lowered)
    total = len(positive_matches) + len(negative_matches)
    if total == 0:
        return 0.0, ()

    score = (len(positive_matches) - len(negative_matches)) / total
    return score, positive_matches + negative_matches


__all__ = ["score_sentiment"]
