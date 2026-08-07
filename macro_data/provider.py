from __future__ import annotations

from typing import Protocol, runtime_checkable

from macro_data.types import MacroObservation


@runtime_checkable
class MacroDataProvider(Protocol):
    """Provider-agnostic interface for a macro/economic data source. FRED,
    a national statistics agency, or any other time-series source
    implements exactly this and nothing more -- fetch a batch of raw
    observations for one series, nothing else. Deliberately mirrors
    news_intelligence.provider.NewsProvider's shape: a thin, swappable
    boundary around one external dependency, with any real analysis
    happening on this platform's side of it, not the vendor's.
    """

    async def fetch_series(self, series_id: str, *, limit: int = 100) -> list[MacroObservation]: ...


__all__ = ["MacroDataProvider"]
