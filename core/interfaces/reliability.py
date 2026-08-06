from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ModuleReliabilityProvider(Protocol):
    """Supplies a source module's empirical historical hit rate for a
    symbol, or None when there isn't enough history to trust yet. Lets
    SignalFusion weight each Evidence contribution by real track record
    without core/ ever importing analytics/ -- HistoricalHitRateStore
    (analytics/hit_rate_store.py) satisfies this Protocol structurally,
    with no import in either direction, exactly the way MT5Connector
    satisfies the Connector Protocol without core/ importing connectors/.
    """

    def hit_rate(self, module_name: str, symbol: str) -> float | None: ...


__all__ = ["ModuleReliabilityProvider"]
