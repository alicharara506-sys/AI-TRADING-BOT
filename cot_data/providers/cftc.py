"""Real CFTC (Commodity Futures Trading Commission) Commitments of Traders
client -- the CFTC's free, public Socrata Open Data API
(https://publicreporting.cftc.gov), no API key or registration required.
Targets the "Legacy Futures Only" dataset (resource id 6dca-aqww), the
classic COT report that covers currency futures (e.g. EURO FX, code
099741) among other financial and commodity contracts.

Needs no credentials to call the live service; this module itself needs
none to import or test either -- see tests/unit/cot_data/test_cftc.py,
which exercises the real request/response handling against a mocked HTTP
transport, the same "real client code, fake the network" pattern used for
macro_data.providers.fred.FredMacroProvider.
"""

from __future__ import annotations

from datetime import date

import httpx

from cot_data.types import CotObservation

_LEGACY_FUTURES_ONLY_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"


def _optional_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    return int(raw)


class CftcCotProvider:
    """Satisfies cot_data.provider.CotDataProvider against the real CFTC
    Socrata API. A position field missing from a given week's row becomes
    CotObservation(...=None), never a fabricated 0.
    """

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, app_token: str | None = None
    ) -> None:
        self._client = client or httpx.AsyncClient()
        self._app_token = app_token

    async def fetch_observations(
        self, contract_market_code: str, *, limit: int = 26
    ) -> list[CotObservation]:
        if not contract_market_code:
            raise ValueError("contract_market_code must not be empty")
        if limit < 1:
            raise ValueError("limit must be >= 1")

        headers = {"X-App-Token": self._app_token} if self._app_token else None
        response = await self._client.get(
            _LEGACY_FUTURES_ONLY_URL,
            params={
                "cftc_contract_market_code": contract_market_code,
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": limit,
            },
            headers=headers,
        )
        response.raise_for_status()
        rows = response.json()

        observations: list[CotObservation] = []
        for row in rows:
            observations.append(
                CotObservation(
                    report_date=date.fromisoformat(row["report_date_as_yyyy_mm_dd"][:10]),
                    contract_market_code=row["cftc_contract_market_code"],
                    market_and_exchange_name=row["market_and_exchange_names"],
                    noncommercial_long=_optional_int(row.get("noncomm_positions_long_all")),
                    noncommercial_short=_optional_int(row.get("noncomm_positions_short_all")),
                    commercial_long=_optional_int(row.get("comm_positions_long_all")),
                    commercial_short=_optional_int(row.get("comm_positions_short_all")),
                    open_interest=_optional_int(row.get("open_interest_all")),
                )
            )
        return observations


__all__ = ["CftcCotProvider"]
