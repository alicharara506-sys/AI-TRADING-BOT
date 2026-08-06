from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Plugin(Protocol):
    plugin_name: str

    def setup(self) -> None: ...
