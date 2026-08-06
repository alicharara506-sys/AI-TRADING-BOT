"""Throughput benchmark for core.event_bus.bus.EventBus.

Measures dispatch throughput under a single publisher with a growing
subscriber fan-out, and under many concurrent publishers sharing one
subscriber -- and asserts that every published event was actually observed
by every subscriber, since a benchmark that silently dropped events would
be worse than useless.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from core.event_bus.bus import EventBus


@dataclass(frozen=True, slots=True)
class _Ping:
    value: int


@dataclass(frozen=True, slots=True)
class EventBusBenchmarkResult:
    label: str
    event_count: int
    elapsed_seconds: float

    @property
    def events_per_second(self) -> float:
        return self.event_count / self.elapsed_seconds if self.elapsed_seconds > 0 else float("inf")


async def _run_single_publisher(
    *, subscriber_count: int, event_count: int
) -> EventBusBenchmarkResult:
    bus = EventBus()
    received = 0

    def _handler(event: _Ping) -> None:
        nonlocal received
        received += 1

    for _ in range(subscriber_count):
        bus.subscribe(_Ping, _handler)

    start = time.perf_counter()
    for i in range(event_count):
        await bus.publish(_Ping(value=i))
    elapsed = time.perf_counter() - start

    expected = subscriber_count * event_count
    if received != expected:
        raise AssertionError(f"dropped events: expected {expected} deliveries, observed {received}")

    return EventBusBenchmarkResult(
        label=f"single publisher, {subscriber_count} subscriber(s)",
        event_count=event_count,
        elapsed_seconds=elapsed,
    )


async def _run_concurrent_publishers(
    *, publisher_count: int, events_per_publisher: int
) -> EventBusBenchmarkResult:
    bus = EventBus()
    received = 0

    def _handler(event: _Ping) -> None:
        nonlocal received
        received += 1

    bus.subscribe(_Ping, _handler)

    async def _publish_all(offset: int) -> None:
        for i in range(events_per_publisher):
            await bus.publish(_Ping(value=offset + i))

    total_events = publisher_count * events_per_publisher
    start = time.perf_counter()
    await asyncio.gather(
        *(_publish_all(p * events_per_publisher) for p in range(publisher_count))
    )
    elapsed = time.perf_counter() - start

    if received != total_events:
        raise AssertionError(
            f"dropped events: expected {total_events} deliveries, observed {received}"
        )

    return EventBusBenchmarkResult(
        label=f"{publisher_count} concurrent publishers, 1 subscriber",
        event_count=total_events,
        elapsed_seconds=elapsed,
    )


async def run() -> list[EventBusBenchmarkResult]:
    return [
        await _run_single_publisher(subscriber_count=1, event_count=20_000),
        await _run_single_publisher(subscriber_count=10, event_count=20_000),
        await _run_single_publisher(subscriber_count=100, event_count=5_000),
        await _run_concurrent_publishers(publisher_count=50, events_per_publisher=1_000),
    ]


if __name__ == "__main__":
    for result in asyncio.run(run()):
        print(f"{result.label:45s} {result.events_per_second:>12,.0f} deliveries/sec "
              f"({result.event_count:,} events in {result.elapsed_seconds * 1000:.1f} ms)")
