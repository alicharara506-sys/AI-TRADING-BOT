from __future__ import annotations

from collections import deque

from core.interfaces.types import Bar


class SimpleMovingAverage:
    """Arithmetic mean of the last `period` closes. None until warmed up."""

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self._period = period
        self._closes: deque[float] = deque(maxlen=period)

    def update(self, bar: Bar) -> float | None:
        self._closes.append(bar.close)
        if len(self._closes) < self._period:
            return None
        return sum(self._closes) / self._period


class ExponentialMovingAverage:
    """Exponentially weighted moving average, seeded with the first close."""

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self._alpha = 2.0 / (period + 1)
        self._value: float | None = None

    def update(self, bar: Bar) -> float | None:
        if self._value is None:
            self._value = bar.close
        else:
            self._value = self._alpha * bar.close + (1 - self._alpha) * self._value
        return self._value


__all__ = ["ExponentialMovingAverage", "SimpleMovingAverage"]
