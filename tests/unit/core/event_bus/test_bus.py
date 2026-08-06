from __future__ import annotations

import pytest

from core.event_bus.bus import EventBus


class _SampleEvent:
    def __init__(self, value: int) -> None:
        self.value = value


class _OtherEvent:
    pass


@pytest.mark.asyncio
async def test_publish_dispatches_to_subscribers() -> None:
    bus = EventBus()
    received: list[int] = []

    async def handler(event: _SampleEvent) -> None:
        received.append(event.value)

    bus.subscribe(_SampleEvent, handler)
    await bus.publish(_SampleEvent(42))

    assert received == [42]


@pytest.mark.asyncio
async def test_publish_ignores_unrelated_subscribers() -> None:
    bus = EventBus()
    received: list[int] = []

    def handler(event: _OtherEvent) -> None:
        received.append(1)

    bus.subscribe(_OtherEvent, handler)
    await bus.publish(_SampleEvent(1))

    assert received == []


@pytest.mark.asyncio
async def test_publish_supports_sync_handlers() -> None:
    bus = EventBus()
    received: list[int] = []

    def handler(event: _SampleEvent) -> None:
        received.append(event.value)

    bus.subscribe(_SampleEvent, handler)
    await bus.publish(_SampleEvent(7))

    assert received == [7]


@pytest.mark.asyncio
async def test_publish_collects_handler_errors_without_stopping_others() -> None:
    bus = EventBus()
    received: list[int] = []

    def failing_handler(event: _SampleEvent) -> None:
        raise ValueError("boom")

    def ok_handler(event: _SampleEvent) -> None:
        received.append(event.value)

    bus.subscribe(_SampleEvent, failing_handler)
    bus.subscribe(_SampleEvent, ok_handler)

    with pytest.raises(ExceptionGroup):
        await bus.publish(_SampleEvent(3))

    assert received == [3]


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received: list[int] = []

    def handler(event: _SampleEvent) -> None:
        received.append(event.value)

    bus.subscribe(_SampleEvent, handler)
    bus.unsubscribe(_SampleEvent, handler)
    await bus.publish(_SampleEvent(9))

    assert received == []
