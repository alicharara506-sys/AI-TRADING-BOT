from __future__ import annotations

from datetime import datetime, timedelta

from core.interfaces.clock import Clock
from core.interfaces.types import ConnectionState


class ReconnectPolicy:
    """Exponential backoff, capped, for reconnect attempts after connection loss."""

    def __init__(
        self,
        *,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
    ) -> None:
        if initial_delay <= 0 or max_delay <= 0 or multiplier <= 1:
            raise ValueError("initial_delay/max_delay must be > 0 and multiplier > 1")
        self._initial_delay = initial_delay
        self._max_delay = max_delay
        self._multiplier = multiplier

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        delay = self._initial_delay * (self._multiplier ** (attempt - 1))
        return min(delay, self._max_delay)


class HeartbeatMonitor:
    """Connected/Degraded/Lost, derived purely from time since the last heartbeat."""

    def __init__(
        self,
        clock: Clock,
        *,
        degraded_after: timedelta,
        lost_after: timedelta,
    ) -> None:
        if lost_after <= degraded_after:
            raise ValueError("lost_after must be greater than degraded_after")
        self._clock = clock
        self._degraded_after = degraded_after
        self._lost_after = lost_after
        self._last_seen: datetime | None = None

    def record_heartbeat(self) -> None:
        self._last_seen = self._clock.now()

    def state(self) -> ConnectionState:
        if self._last_seen is None:
            return ConnectionState.DISCONNECTED
        elapsed = self._clock.now() - self._last_seen
        if elapsed >= self._lost_after:
            return ConnectionState.LOST
        if elapsed >= self._degraded_after:
            return ConnectionState.DEGRADED
        return ConnectionState.CONNECTED


__all__ = ["HeartbeatMonitor", "ReconnectPolicy"]
