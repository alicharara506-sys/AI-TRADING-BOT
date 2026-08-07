from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class CotObservation:
    """One weekly CFTC Commitments of Traders reading for one contract
    market, exactly as published -- provider-agnostic, the same "raw item
    before any analysis" role macro_data.types.MacroObservation plays for
    FRED series. Position counts are None when the source genuinely omits
    a field for that week -- never silently coerced to 0, which would
    fabricate a position count that was never actually published.
    """

    report_date: date
    contract_market_code: str
    market_and_exchange_name: str
    noncommercial_long: int | None
    noncommercial_short: int | None
    commercial_long: int | None
    commercial_short: int | None
    open_interest: int | None


__all__ = ["CotObservation"]
