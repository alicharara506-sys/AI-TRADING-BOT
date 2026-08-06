from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class ContainerError(Exception):
    pass


class Container:
    """Minimal DI container: register instances or factories, resolve by interface type."""

    def __init__(self) -> None:
        self._factories: dict[type, Callable[[], object]] = {}
        self._singletons: dict[type, object] = {}
        self._singleton_types: set[type] = set()

    def register_instance(self, interface: type[T], instance: T) -> None:
        self._singletons[interface] = instance
        self._singleton_types.add(interface)

    def register_factory(
        self,
        interface: type[T],
        factory: Callable[[], T],
        *,
        singleton: bool = True,
    ) -> None:
        self._factories[interface] = factory
        if singleton:
            self._singleton_types.add(interface)
        self._singletons.pop(interface, None)

    def resolve(self, interface: type[T]) -> T:
        if interface in self._singletons:
            return self._singletons[interface]  # type: ignore[return-value]

        factory = self._factories.get(interface)
        if factory is None:
            raise ContainerError(f"No registration for {interface!r}")

        instance = factory()
        if interface in self._singleton_types:
            self._singletons[interface] = instance
        return instance  # type: ignore[return-value]


__all__ = ["Container", "ContainerError"]
