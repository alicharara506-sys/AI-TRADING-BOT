from __future__ import annotations

from datetime import UTC, datetime

import pytest

from news_intelligence.dedup import Deduplicator, jaccard_similarity
from news_intelligence.types import NewsItem


def _item(item_id: str, headline: str, body: str = "") -> NewsItem:
    return NewsItem(
        item_id=item_id, source="wire", headline=headline, body=body,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_jaccard_similarity_identical_and_disjoint_sets() -> None:
    assert jaccard_similarity(frozenset(), frozenset()) == 1.0
    assert jaccard_similarity(frozenset({"a"}), frozenset()) == 0.0
    assert jaccard_similarity(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0
    assert jaccard_similarity(frozenset({"a"}), frozenset({"b"})) == 0.0


def test_first_item_is_never_a_duplicate() -> None:
    dedup = Deduplicator()

    assert dedup.check(_item("1", "Fed holds rates steady")) is None


def test_exact_repeat_is_detected_as_a_duplicate() -> None:
    dedup = Deduplicator()
    dedup.check(_item("1", "Fed holds rates steady", "No policy change"))

    result = dedup.check(_item("2", "Fed holds rates steady", "No policy change"))

    assert result == "1"


def test_near_duplicate_detected_when_similarity_clears_the_threshold() -> None:
    dedup = Deduplicator(near_duplicate_threshold=0.3)
    dedup.check(_item("1", "Fed holds rates steady", "No change to policy"))

    result = dedup.check(
        _item(
            "2",
            "Federal Reserve holds interest rates steady",
            "No change to monetary policy today",
        )
    )

    assert result == "1"


def test_dissimilar_items_are_not_flagged_as_duplicates() -> None:
    dedup = Deduplicator()
    dedup.check(_item("1", "Fed holds rates steady"))

    result = dedup.check(_item("2", "Completely unrelated tech news about smartphones"))

    assert result is None


def test_duplicate_of_a_duplicate_resolves_to_the_original() -> None:
    dedup = Deduplicator()
    dedup.check(_item("1", "Fed holds rates steady", "No change"))
    dedup.check(_item("2", "Fed holds rates steady", "No change"))  # exact dup of 1

    result = dedup.check(_item("3", "Fed holds rates steady", "No change"))

    assert result == "1"


def test_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError, match="near_duplicate_threshold"):
        Deduplicator(near_duplicate_threshold=0.0)
    with pytest.raises(ValueError, match="near_duplicate_threshold"):
        Deduplicator(near_duplicate_threshold=1.5)
