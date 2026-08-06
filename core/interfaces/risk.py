from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.interfaces.types import OrderRequest, TradeSignal


@runtime_checkable
class SizingModel(Protocol):
    def size(self, signal: TradeSignal, *, equity: float) -> float: ...


@runtime_checkable
class RiskModel(Protocol):
    def evaluate_signal(self, signal: TradeSignal) -> TradeSignal | None: ...

    def evaluate_order(self, request: OrderRequest) -> OrderRequest | None: ...
