from __future__ import annotations

from typing import Protocol, runtime_checkable

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

    def size(
        self, signal: TradeSignal, *, equity: float, stop_distance: float | None = None
    ) -> float:
        return self._volume


class RiskPercentSizingModel:
    """Equity-aware dynamic position sizing: risk a fixed fraction of equity
    per trade, with size derived from the actual stop distance so a wider
    stop (more volatile symbol/setup) automatically trades a smaller
    position for the same dollar risk -- the standard "risk-based" sizing
    formula, size = (equity * risk_percent) / stop_distance. Sizes to zero
    (not a guess) whenever no real stop_distance is available, since this
    model's entire premise is knowing the actual distance being risked.
    """

    def __init__(self, risk_percent: float) -> None:
        if not 0.0 < risk_percent <= 1.0:
            raise ValueError("risk_percent must be in (0.0, 1.0]")
        self._risk_percent = risk_percent

    def size(
        self, signal: TradeSignal, *, equity: float, stop_distance: float | None = None
    ) -> float:
        if stop_distance is None or stop_distance <= 0:
            return 0.0
        return (equity * self._risk_percent) / stop_distance


@runtime_checkable
class KellyStatisticsProvider(Protocol):
    """What KellySizingModel needs to know about a symbol's real historical
    trade outcomes. A narrow Protocol (not a concrete store shipped here,
    the same pattern as NewsProvider/LLMProvider elsewhere in this
    platform) so any real backing store -- or a fake, in tests -- can
    supply it.
    """

    def win_rate(self, symbol: str) -> float | None: ...

    def win_loss_ratio(self, symbol: str) -> float | None: ...

    def sample_count(self, symbol: str) -> int: ...


class KellySizingModel:
    """Data-gated Kelly Criterion sizing: f* = win_rate - (1 - win_rate) /
    win_loss_ratio, the fraction of equity the Kelly formula says to risk
    given a symbol's real historical win rate and average win/loss payoff
    ratio. Sizes to zero -- never a fabricated guess -- whenever there
    isn't yet `min_samples` worth of real history for the symbol, or the
    formula itself comes out non-positive (no edge). Clamped to
    `max_kelly_fraction` since full Kelly is notoriously high-variance in
    practice; traders conventionally risk a fraction of full Kelly.
    """

    def __init__(
        self,
        statistics: KellyStatisticsProvider,
        *,
        min_samples: int = 30,
        max_kelly_fraction: float = 0.25,
    ) -> None:
        if min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        if not 0.0 < max_kelly_fraction <= 1.0:
            raise ValueError("max_kelly_fraction must be in (0.0, 1.0]")
        self._statistics = statistics
        self._min_samples = min_samples
        self._max_kelly_fraction = max_kelly_fraction

    def size(
        self, signal: TradeSignal, *, equity: float, stop_distance: float | None = None
    ) -> float:
        if stop_distance is None or stop_distance <= 0:
            return 0.0

        symbol = signal.symbol.canonical
        if self._statistics.sample_count(symbol) < self._min_samples:
            return 0.0

        win_rate = self._statistics.win_rate(symbol)
        win_loss_ratio = self._statistics.win_loss_ratio(symbol)
        if win_rate is None or win_loss_ratio is None or win_loss_ratio <= 0:
            return 0.0

        kelly_fraction = win_rate - (1.0 - win_rate) / win_loss_ratio
        kelly_fraction = max(0.0, min(kelly_fraction, self._max_kelly_fraction))
        if kelly_fraction <= 0.0:
            return 0.0

        return (equity * kelly_fraction) / stop_distance


__all__ = [
    "FixedVolumeSizingModel",
    "KellySizingModel",
    "KellyStatisticsProvider",
    "RiskPercentSizingModel",
]
