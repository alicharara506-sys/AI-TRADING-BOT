from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.event_bus.bus import EventBus
from core.kernel.container import Container


@runtime_checkable
class Startable(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class Kernel:
    """Owns the Container and EventBus for a process, and drives component lifecycle."""

    def __init__(
        self, container: Container | None = None, event_bus: EventBus | None = None
    ) -> None:
        self.container = container or Container()
        self.event_bus = event_bus or EventBus()
        self.container.register_instance(EventBus, self.event_bus)
        self._components: list[Startable] = []

    def register_component(self, component: Startable) -> None:
        self._components.append(component)

    async def start(self) -> None:
        for component in self._components:
            await component.start()

    async def stop(self) -> None:
        for component in reversed(self._components):
            await component.stop()


__all__ = ["Kernel", "Startable"]
