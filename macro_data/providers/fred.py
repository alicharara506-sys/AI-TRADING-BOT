"""Real FRED (Federal Reserve Economic Data) API client -- St. Louis Fed's
free, public economic-data REST API (https://fred.stlouisfed.org/docs/api/fred/).

Needs a free API key (https://fred.stlouisfed.org/docs/api/api_key.html) to
actually call the live service; this module itself needs no key to import
or test -- see tests/unit/macro_data/test_fred.py, which exercises the real
request/response handling against a mocked HTTP transport, the same
"real client code, fake the network" pattern this platform already uses
for MT5Api/NewsProvider.
"""

from __future__ import annotations

from datetime import date

import httpx

from macro_data.types import MacroObservation

_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


class FredMacroProvider:
    """Satisfies macro_data.provider.MacroDataProvider against the real FRED
    API. Missing observations (FRED represents these as the literal string
    "." -- a gap the series genuinely has, e.g. before it started) become
    MacroObservation(value=None), never a fabricated 0.0.
    """

    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._client = client or httpx.AsyncClient()

    async def fetch_series(self, series_id: str, *, limit: int = 100) -> list[MacroObservation]:
        if not series_id:
            raise ValueError("series_id must not be empty")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        response = await self._client.get(
            _OBSERVATIONS_URL,
            params={
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
        )
        response.raise_for_status()
        payload = response.json()

        observations: list[MacroObservation] = []
        for row in payload.get("observations", []):
            raw_value = row.get("value")
            value = None if raw_value in (None, ".") else float(raw_value)
            observations.append(
                MacroObservation(
                    series_id=series_id,
                    observed_on=date.fromisoformat(row["date"]),
                    value=value,
                )
            )
        return observations


__all__ = ["FredMacroProvider"]
