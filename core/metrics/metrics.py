from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Protocol, runtime_checkable


@runtime_checkable
class Metrics(Protocol):
    def increment(
        self, name: str, *, value: float = 1.0, tags: dict[str, str] | None = None
    ) -> None: ...

    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None: ...

    def gauge(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None: ...


class InMemoryMetrics:
    """Reference Metrics implementation. A Prometheus-backed adapter implements the
    same protocol later without any caller changing."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._gauges: dict[str, float] = {}

    def increment(
        self, name: str, *, value: float = 1.0, tags: dict[str, str] | None = None
    ) -> None:
        key = self._key(name, tags)
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        key = self._key(name, tags)
        with self._lock:
            self._histograms[key].append(value)

    def gauge(self, name: str, value: float, *, tags: dict[str, str] | None = None) -> None:
        key = self._key(name, tags)
        with self._lock:
            self._gauges[key] = value

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "histograms": {k: list(v) for k, v in self._histograms.items()},
                "gauges": dict(self._gauges),
            }

    @staticmethod
    def _key(name: str, tags: dict[str, str] | None) -> str:
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"


__all__ = ["InMemoryMetrics", "Metrics"]
