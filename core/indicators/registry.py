from __future__ import annotations

from collections.abc import Callable

from core.interfaces.indicator import Indicator


class IndicatorRegistryError(Exception):
    pass


class IndicatorRegistry:
    """Named indicator factories, so live trading, backtesting, optimization, and
    analytics all construct the exact same indicator implementation by name."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Indicator]] = {}

    def register(self, name: str, factory: Callable[[], Indicator]) -> None:
        if name in self._factories:
            raise IndicatorRegistryError(f"Indicator '{name}' is already registered")
        self._factories[name] = factory

    def create(self, name: str) -> Indicator:
        factory = self._factories.get(name)
        if factory is None:
            raise IndicatorRegistryError(f"No indicator registered as '{name}'")
        return factory()

    def names(self) -> list[str]:
        return sorted(self._factories)


__all__ = ["IndicatorRegistry", "IndicatorRegistryError"]
