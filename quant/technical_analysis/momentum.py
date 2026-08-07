from __future__ import annotations

from collections.abc import Sequence

from core.interfaces.types import Bar, Direction, Evidence, MarketContext
from quant.technical_analysis.volatility import compute_atr


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    """Exponential moving average over a plain float series, seeded with the
    first value -- the exact same seeding convention as
    core.indicators.trend.ExponentialMovingAverage, just operating on any
    float sequence (a MACD signal line is an EMA of the MACD line, not of a
    Bar's close, so that Bar-typed streaming class can't be reused directly).
    """
    alpha = 2.0 / (period + 1)
    ema = values[0]
    result = [ema]
    for value in values[1:]:
        ema = alpha * value + (1 - alpha) * ema
        result.append(ema)
    return result


def compute_macd(
    bars: Sequence[Bar], *, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> tuple[float, float, float] | None:
    """Standard MACD: (macd_line, signal_line, histogram) where macd_line is
    fast EMA minus slow EMA of closes, and signal_line is the EMA of
    macd_line. None until there's enough history to seed both EMA legs and
    the signal line's own EMA.
    """
    if fast_period < 1 or slow_period < 1 or signal_period < 1:
        raise ValueError("fast_period, slow_period, and signal_period must all be >= 1")
    if slow_period <= fast_period:
        raise ValueError("slow_period must exceed fast_period")
    if len(bars) < slow_period + signal_period:
        return None

    closes = [bar.close for bar in bars]
    fast_ema = _ema_series(closes, fast_period)
    slow_ema = _ema_series(closes, slow_period)
    macd_line = [f - s for f, s in zip(fast_ema, slow_ema, strict=True)]
    signal_line = _ema_series(macd_line, signal_period)
    histogram = macd_line[-1] - signal_line[-1]
    return macd_line[-1], signal_line[-1], histogram


class MacdCrossoverModule:
    """MACD histogram sign-flip: the MACD line crossing its own signal line is
    the standard MACD trade trigger. Confidence is the crossover's size
    relative to ATR (a volatility-relative scale, since a MACD histogram
    value has no natural units of its own) -- same normalization approach
    AtrVolatilityBreakoutModule already uses for its own trigger size.
    """

    name = "macd_crossover"

    def __init__(
        self,
        *,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        atr_period: int = 14,
    ) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._signal_period = signal_period
        self._atr_period = atr_period

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        needed = self._slow_period + self._signal_period + 1
        if len(bars) < needed:
            return []

        previous = compute_macd(
            bars[:-1],
            fast_period=self._fast_period,
            slow_period=self._slow_period,
            signal_period=self._signal_period,
        )
        current = compute_macd(
            bars,
            fast_period=self._fast_period,
            slow_period=self._slow_period,
            signal_period=self._signal_period,
        )
        if previous is None or current is None:
            return []

        prev_histogram, curr_histogram = previous[2], current[2]
        crossed_up = prev_histogram <= 0 and curr_histogram > 0
        crossed_down = prev_histogram >= 0 and curr_histogram < 0
        if not crossed_up and not crossed_down:
            return []

        atr = compute_atr(bars, period=self._atr_period)
        if atr is None or atr <= 0:
            return []

        confidence = min(abs(curr_histogram) / atr, 1.0)
        if confidence <= 0.0:
            return []

        direction = Direction.LONG if crossed_up else Direction.SHORT
        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={
                    "macd_line": current[0],
                    "signal_line": current[1],
                    "histogram": curr_histogram,
                },
            )
        ]


def _directional_movement_and_true_range(
    bars: Sequence[Bar],
) -> tuple[list[float], list[float], list[float]]:
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_range: list[float] = []
    for previous, current in zip(bars, bars[1:], strict=False):
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)
        true_range.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return plus_dm, minus_dm, true_range


def _trailing_mean_series(values: Sequence[float], period: int) -> list[float]:
    """One trailing-mean value per `period`-wide window, sliding by 1 bar --
    the same trailing-mean simplification quant.technical_analysis.volatility
    already documents using instead of Wilder's full recursive smoothing.
    """
    return [sum(values[i : i + period]) / period for i in range(len(values) - period + 1)]


def compute_adx(bars: Sequence[Bar], *, period: int = 14) -> tuple[float, float, float] | None:
    """(plus_di, minus_di, adx): Wilder's Directional Movement Index, with the
    +DI/-DI legs built from a simple trailing mean of +DM/-DM/true-range
    (the same simplification already made for ATR) rather than Wilder's
    recursive smoothing; the final ADX value itself is a genuine mean of the
    last `period` DX values, matching the standard definition. None until
    there's enough history for both the DI trailing windows and a full
    `period`-long DX average.
    """
    if period < 2:
        raise ValueError("period must be >= 2")
    if len(bars) < 2 * period + 1:
        return None

    plus_dm, minus_dm, true_range = _directional_movement_and_true_range(bars)
    plus_di_series = [
        100 * plus / tr if tr > 0 else 0.0
        for plus, tr in zip(
            _trailing_mean_series(plus_dm, period), _trailing_mean_series(true_range, period),
            strict=True,
        )
    ]
    minus_di_series = [
        100 * minus / tr if tr > 0 else 0.0
        for minus, tr in zip(
            _trailing_mean_series(minus_dm, period), _trailing_mean_series(true_range, period),
            strict=True,
        )
    ]
    dx_series = [
        100 * abs(plus - minus) / (plus + minus) if (plus + minus) > 0 else 0.0
        for plus, minus in zip(plus_di_series, minus_di_series, strict=True)
    ]
    if len(dx_series) < period:
        return None

    adx = sum(dx_series[-period:]) / period
    return plus_di_series[-1], minus_di_series[-1], adx


class AdxTrendModule:
    """ADX trend-strength filter: when ADX clears `trend_threshold` (Wilder's
    own convention: 25 marks a "trending" market), the side with the higher
    directional index is evidence of that trend's direction. Below the
    threshold the market is ranging by this measure -- deliberately no
    evidence either way, since ADX says nothing about direction on its own.
    """

    name = "adx_trend"

    def __init__(self, *, period: int = 14, trend_threshold: float = 25.0) -> None:
        if period < 2:
            raise ValueError("period must be >= 2")
        if not 0.0 < trend_threshold < 100.0:
            raise ValueError("trend_threshold must be in (0.0, 100.0)")
        self._period = period
        self._trend_threshold = trend_threshold

    def analyze(self, context: MarketContext) -> list[Evidence]:
        result = compute_adx(context.bars, period=self._period)
        if result is None:
            return []

        plus_di, minus_di, adx = result
        if adx < self._trend_threshold or plus_di == minus_di:
            return []

        confidence = min((adx - self._trend_threshold) / (100.0 - self._trend_threshold), 1.0)
        if confidence <= 0.0:
            return []

        direction = Direction.LONG if plus_di > minus_di else Direction.SHORT
        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={"adx": adx, "plus_di": plus_di, "minus_di": minus_di},
            )
        ]


__all__ = ["AdxTrendModule", "MacdCrossoverModule", "compute_adx", "compute_macd"]
