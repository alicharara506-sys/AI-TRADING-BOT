from __future__ import annotations

from core.interfaces.types import Bar


class RelativeStrengthIndex:
    """Wilder's RSI: Wilder-smoothed average gain/loss over `period` bars."""

    def __init__(self, period: int = 14) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self._period = period
        self._prev_close: float | None = None
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self._count = 0

    def update(self, bar: Bar) -> float | None:
        close = bar.close
        if self._prev_close is None:
            self._prev_close = close
            return None

        change = close - self._prev_close
        self._prev_close = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        self._count += 1

        if self._count <= self._period:
            self._avg_gain += gain
            self._avg_loss += loss
            if self._count < self._period:
                return None
            self._avg_gain /= self._period
            self._avg_loss /= self._period
        else:
            self._avg_gain = (self._avg_gain * (self._period - 1) + gain) / self._period
            self._avg_loss = (self._avg_loss * (self._period - 1) + loss) / self._period

        if self._avg_loss == 0:
            return 100.0
        relative_strength = self._avg_gain / self._avg_loss
        return 100.0 - (100.0 / (1.0 + relative_strength))


__all__ = ["RelativeStrengthIndex"]
