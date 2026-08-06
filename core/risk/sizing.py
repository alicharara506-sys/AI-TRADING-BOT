from __future__ import annotations

from core.interfaces.types import TradeSignal


class FixedVolumeSizingModel:
    """The simplest real sizing model: every approved signal trades the same fixed
    volume, regardless of equity or confidence. Kelly/ATR/volatility-based sizing
    (per the architecture's pluggable SizingModel interface) are later additions
    behind the same Protocol -- this is a genuine, commonly used sizing choice in
    its own right, not a stand-in for them.
    """

    def __init__(self, volume: float) -> None:
        if volume <= 0:
            raise ValueError("volume must be > 0")
        self._volume = volume

    def size(self, signal: TradeSignal, *, equity: float) -> float:
        return self._volume


__all__ = ["FixedVolumeSizingModel"]
