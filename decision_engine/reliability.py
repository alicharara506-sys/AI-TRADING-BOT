from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HistoricalReliabilityStore(Protocol):
    """What DecisionEngine needs to judge how much real history backs a
    signal's contributing modules -- a superset of
    core.interfaces.reliability.ModuleReliabilityProvider (which only needs
    hit_rate() for SignalFusion's purposes). decision_engine/ is an
    outer-layer package, so it could import analytics.hit_rate_store
    directly, but depending on this narrower Protocol instead keeps
    DecisionEngine swappable and trivially testable against a fake, the
    same interface-segregation choice made throughout this platform.
    HistoricalHitRateStore satisfies this structurally with no code change.
    """

    def hit_rate(self, module_name: str, symbol: str) -> float | None: ...

    def sample_count(self, module_name: str, symbol: str) -> int: ...


__all__ = ["HistoricalReliabilityStore"]
