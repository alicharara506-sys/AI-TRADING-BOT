from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class MacroObservation:
    """One dated reading of one macro/economic time series, exactly as
    published by the source -- provider-agnostic, the same "raw item
    before any analysis" role news_intelligence.types.NewsItem plays for
    news. `value` is None for a real published gap (FRED itself reports
    some observations as missing, e.g. before a series started, or a data
    revision not yet available) -- never silently coerced to 0.0, which
    would fabricate a reading that was never actually published.
    """

    series_id: str
    observed_on: date
    value: float | None


__all__ = ["MacroObservation"]
