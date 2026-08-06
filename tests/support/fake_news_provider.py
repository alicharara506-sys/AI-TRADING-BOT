from __future__ import annotations

from dataclasses import dataclass, field

from news_intelligence.types import NewsItem


@dataclass
class FakeNewsProvider:
    """Configurable NewsProvider test double. Set `items` to whatever
    fetch_latest() should return."""

    items: list[NewsItem] = field(default_factory=list)

    async def fetch_latest(self, *, limit: int = 50) -> list[NewsItem]:
        return self.items[:limit]


__all__ = ["FakeNewsProvider"]
