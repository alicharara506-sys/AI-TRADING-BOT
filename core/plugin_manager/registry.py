from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class PluginRegistryError(Exception):
    pass


class PluginRegistry(Generic[T]):
    """Named factories for one plugin kind. This is the mechanism every extension
    point in the platform resolves through -- indicators first, strategies here,
    risk models/sizing models/data providers/reports as each of those arrives --
    so "everything is a plugin" is one reused pattern, not N bespoke registries.
    """

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], T]] = {}

    def register(self, name: str, factory: Callable[[], T]) -> None:
        if name in self._factories:
            raise PluginRegistryError(f"Plugin '{name}' is already registered")
        self._factories[name] = factory

    def create(self, name: str) -> T:
        factory = self._factories.get(name)
        if factory is None:
            raise PluginRegistryError(f"No plugin registered as '{name}'")
        return factory()

    def names(self) -> list[str]:
        return sorted(self._factories)


__all__ = ["PluginRegistry", "PluginRegistryError"]
