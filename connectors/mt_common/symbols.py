from __future__ import annotations

from dataclasses import dataclass

from core.interfaces.types import Symbol


@dataclass(frozen=True, slots=True)
class SymbolMapper:
    """Translates between our canonical Symbol and a broker's suffixed symbol name
    (e.g. "EURUSD" <-> "EURUSD.m"), so the rest of the platform never sees broker
    suffix conventions."""

    suffix: str = ""

    def to_broker(self, symbol: Symbol) -> str:
        return f"{symbol.canonical}{self.suffix}"

    def from_broker(self, broker_symbol_name: str) -> Symbol:
        name = broker_symbol_name
        if self.suffix and name.endswith(self.suffix):
            name = name[: -len(self.suffix)]
        return Symbol(name=name, broker_suffix=self.suffix)


__all__ = ["SymbolMapper"]
