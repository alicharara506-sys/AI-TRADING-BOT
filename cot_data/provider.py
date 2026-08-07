from __future__ import annotations

from typing import Protocol, runtime_checkable

from cot_data.types import CotObservation


@runtime_checkable
class CotDataProvider(Protocol):
    """Provider-agnostic interface for a Commitments of Traders positioning
    source. Deliberately mirrors macro_data.provider.MacroDataProvider's
    shape: a thin, swappable boundary around one external dependency --
    fetch a batch of raw observations for one contract market, nothing
    else. Any real analysis happens on this platform's side of it, not the
    vendor's.
    """

    async def fetch_observations(
        self, contract_market_code: str, *, limit: int = 26
    ) -> list[CotObservation]: ...


__all__ = ["CotDataProvider"]
