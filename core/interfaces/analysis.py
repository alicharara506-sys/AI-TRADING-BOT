from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.interfaces.types import Evidence, MarketContext


@runtime_checkable
class AnalysisModule(Protocol):
    name: str

    def analyze(self, context: MarketContext) -> list[Evidence]: ...
