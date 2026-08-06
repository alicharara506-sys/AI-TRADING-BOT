from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.interfaces.types import Bar


@runtime_checkable
class Indicator(Protocol):
    def update(self, bar: Bar) -> float | None: ...
