from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

TEvent = TypeVar("TEvent")
Handler = Callable[[TEvent], Awaitable[None] | None]


class EventBus:
    """Typed async pub/sub. Dispatch is by exact event type, not subclass."""

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Handler[Any]]] = defaultdict(list)

    def subscribe(self, event_type: type[TEvent], handler: Handler[TEvent]) -> None:
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: type[TEvent], handler: Handler[TEvent]) -> None:
        self._subscribers[event_type].remove(handler)

    async def publish(self, event: object) -> None:
        handlers = list(self._subscribers.get(type(event), ()))
        errors: list[Exception] = []
        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001 - collected, not swallowed
                errors.append(exc)
        if errors:
            raise ExceptionGroup(
                f"{len(errors)} subscriber(s) failed handling {type(event).__name__}",
                errors,
            )


__all__ = ["EventBus", "Handler"]
