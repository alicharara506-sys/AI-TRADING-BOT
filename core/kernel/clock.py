from __future__ import annotations

from datetime import UTC, datetime, timedelta


class LiveClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class TestClock:
    """Deterministic clock for backtests: advances only when told to."""

    __test__ = False  # not a pytest test class, despite the name

    def __init__(self, start: datetime) -> None:
        self._current = start

    def now(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> None:
        self._current += delta

    def set(self, moment: datetime) -> None:
        self._current = moment


__all__ = ["LiveClock", "TestClock"]
