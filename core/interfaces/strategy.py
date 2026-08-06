from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.interfaces.types import Bar, TradeSignal


@runtime_checkable
class Strategy(Protocol):
    strategy_name: str

    def on_bar(self, bar: Bar) -> TradeSignal | None: ...
