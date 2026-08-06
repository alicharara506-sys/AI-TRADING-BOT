from __future__ import annotations

import hashlib
import re

from news_intelligence.types import NewsItem

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _normalize(item: NewsItem) -> str:
    return f"{item.headline.strip().lower()} {item.body.strip().lower()}"


def _tokenize(item: NewsItem) -> frozenset[str]:
    return frozenset(_TOKEN_PATTERN.findall(_normalize(item)))


def _content_hash(item: NewsItem) -> str:
    return hashlib.sha256(_normalize(item).encode("utf-8")).hexdigest()


def jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class Deduplicator:
    """Exact-hash dedup for byte-identical republishes (the same wire item
    from two feeds, or a provider's own retry), plus near-duplicate
    detection via token-set Jaccard similarity for the far more common
    case: two outlets covering the same event in different words. Every
    item is remembered regardless of outcome, so a duplicate-of-a-duplicate
    still correctly resolves back to the first item ever seen for that
    story.
    """

    def __init__(self, *, near_duplicate_threshold: float = 0.75) -> None:
        if not (0.0 < near_duplicate_threshold <= 1.0):
            raise ValueError("near_duplicate_threshold must be in (0, 1]")
        self._threshold = near_duplicate_threshold
        self._hash_to_id: dict[str, str] = {}
        self._seen: list[tuple[str, frozenset[str]]] = []

    def check(self, item: NewsItem) -> str | None:
        """Returns the item_id of the earlier item this duplicates, or None
        if it's new. Always records the item as seen either way.
        """
        content_hash = _content_hash(item)
        existing_id = self._hash_to_id.get(content_hash)
        if existing_id is not None:
            return existing_id

        tokens = _tokenize(item)
        for other_id, other_tokens in self._seen:
            if jaccard_similarity(tokens, other_tokens) >= self._threshold:
                self._hash_to_id[content_hash] = other_id
                return other_id

        self._hash_to_id[content_hash] = item.item_id
        self._seen.append((item.item_id, tokens))
        return None


__all__ = ["Deduplicator", "jaccard_similarity"]
