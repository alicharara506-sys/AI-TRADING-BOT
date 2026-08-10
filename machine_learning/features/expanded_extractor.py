from __future__ import annotations

from collections.abc import Sequence

from core.indicators.momentum import RelativeStrengthIndex
from core.interfaces.types import Bar, MarketContext
from quant.technical_analysis.regime import compute_atr_percentile_rank
from quant.technical_analysis.volatility import compute_atr
from quant.technical_analysis.vwap import compute_vwap

_FEATURE_NAMES = [
    "rsi_zscore",
    "directional_efficiency",
    "tick_volume_ratio",
    "atr_percentile",
    "vwap_deviation",
]

# tick_volume_ratio is clipped at this multiple of its trailing average
# before being squashed to [0, 1] -- a bar with 3x+ the recent average
# volume is already an extreme outlier, so clipping keeps one freak bar
# from dominating the normalized feature's scale.
_MAX_TICK_VOLUME_RATIO = 3.0


def _rsi_series(bars: Sequence[Bar], *, period: int) -> list[float]:
    rsi = RelativeStrengthIndex(period=period)
    values: list[float] = []
    for bar in bars:
        value = rsi.update(bar)
        if value is not None:
            values.append(value)
    return values


def compute_rsi_zscore(
    bars: Sequence[Bar], *, rsi_period: int = 14, zscore_window: int = 50
) -> float | None:
    """How extreme the current RSI(`rsi_period`) reading is relative to its
    own last `zscore_window` values -- a z-score, not the raw 0-100 RSI
    scale, so a reading of (say) 2.0 means "two standard deviations above
    this symbol's own recent RSI distribution" regardless of where that
    symbol's RSI typically sits. Replays core.indicators.momentum's own
    Wilder-smoothed RelativeStrengthIndex rather than reimplementing RSI.
    """
    if rsi_period < 1:
        raise ValueError("rsi_period must be >= 1")
    if zscore_window < 2:
        raise ValueError("zscore_window must be >= 2")
    series = _rsi_series(bars, period=rsi_period)
    if len(series) < zscore_window:
        return None
    window = series[-zscore_window:]
    mean = sum(window) / len(window)
    variance = sum((value - mean) ** 2 for value in window) / (len(window) - 1)
    std = variance**0.5
    if std < 1e-12:
        return 0.0
    return float((window[-1] - mean) / std)


def compute_directional_efficiency(bars: Sequence[Bar], *, period: int = 14) -> float | None:
    """Kaufman's Efficiency Ratio: net directional displacement over the
    last `period` bars divided by the total path length traveled to get
    there -- 1.0 for a straight, noise-free move, near 0.0 for pure chop.
    A genuine path-efficiency measure, distinct from ADX (which measures
    directional-movement strength, not path efficiency) and not previously
    implemented anywhere in this platform.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(bars) < period + 1:
        return None
    closes = [bar.close for bar in bars[-(period + 1) :]]
    net_change = abs(closes[-1] - closes[0])
    path_length = sum(abs(b - a) for a, b in zip(closes, closes[1:], strict=False))
    if path_length <= 0:
        return 0.0
    return net_change / path_length


def compute_tick_volume_ratio(bars: Sequence[Bar], *, period: int = 20) -> float | None:
    """The most recent bar's tick volume divided by the average of the
    `period` bars before it -- how unusually active (>1) or quiet (<1) the
    latest bar was relative to its own recent history. None when the
    trailing average volume is zero (an illiquid symbol/timeframe, the same
    condition compute_vwap already declines to divide by).
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if len(bars) < period + 1:
        return None
    window = bars[-(period + 1) : -1]
    average_volume = sum(bar.volume for bar in window) / len(window)
    if average_volume <= 0:
        return None
    return bars[-1].volume / average_volume


def compute_vwap_deviation(
    bars: Sequence[Bar], *, vwap_period: int = 20, atr_period: int = 14
) -> float | None:
    """Current close's distance from a trailing-window VWAP, ATR-normalized
    -- the same "a raw price-VWAP distance has no natural bound of its own,
    scale by ATR" convention AnchoredVwapModule already uses. Deliberately
    a rolling window, not a session/swing anchor: this feature extractor is
    timeframe-agnostic (it never knows whether it's fed 15M or 1H bars), so
    it cannot assume a calendar session boundary the way
    AnchoredVwapModule's swing-anchored version can.
    """
    vwap = compute_vwap(bars, period=vwap_period)
    if vwap is None:
        return None
    atr = compute_atr(bars, period=atr_period)
    if atr is None or atr <= 0:
        return None
    return (bars[-1].close - vwap) / atr


class ExpandedFeatureExtractor:
    """A second, richer ML feature set alongside FeatureExtractor's original
    five (return_1/sma_distance/ema_distance/rsi/volatility): RSI z-score,
    Kaufman directional efficiency, tick-volume ratio, ATR percentile rank,
    and ATR-normalized VWAP deviation -- every one pure arithmetic over
    existing indicator/quant primitives, no new dependency. Kept separate
    from FeatureExtractor rather than replacing it: CalibratedClassifier and
    MLPredictionModule already depend on FeatureExtractor's exact 5-feature
    contract, and nothing here changes that. RuleForest and PatternMatcher
    (machine_learning/models/) are what actually consume this richer set.
    """

    def __init__(
        self,
        *,
        rsi_period: int = 14,
        rsi_zscore_window: int = 50,
        directional_efficiency_period: int = 14,
        volume_ratio_period: int = 20,
        atr_period: int = 14,
        atr_percentile_lookback: int = 100,
        vwap_period: int = 20,
    ) -> None:
        self._rsi_period = rsi_period
        self._rsi_zscore_window = rsi_zscore_window
        self._directional_efficiency_period = directional_efficiency_period
        self._volume_ratio_period = volume_ratio_period
        self._atr_period = atr_period
        self._atr_percentile_lookback = atr_percentile_lookback
        self._vwap_period = vwap_period

    def feature_names(self) -> list[str]:
        return list(_FEATURE_NAMES)

    def extract(self, context: MarketContext) -> dict[str, float] | None:
        bars = context.bars
        rsi_zscore = compute_rsi_zscore(
            bars, rsi_period=self._rsi_period, zscore_window=self._rsi_zscore_window
        )
        directional_efficiency = compute_directional_efficiency(
            bars, period=self._directional_efficiency_period
        )
        tick_volume_ratio = compute_tick_volume_ratio(bars, period=self._volume_ratio_period)
        atr_percentile = compute_atr_percentile_rank(
            bars, atr_period=self._atr_period, lookback=self._atr_percentile_lookback
        )
        vwap_deviation = compute_vwap_deviation(
            bars, vwap_period=self._vwap_period, atr_period=self._atr_period
        )

        if (
            rsi_zscore is None
            or directional_efficiency is None
            or tick_volume_ratio is None
            or atr_percentile is None
            or vwap_deviation is None
        ):
            return None

        clipped_volume_ratio = min(tick_volume_ratio, _MAX_TICK_VOLUME_RATIO)
        return {
            "rsi_zscore": rsi_zscore,
            "directional_efficiency": directional_efficiency,
            "tick_volume_ratio": clipped_volume_ratio / _MAX_TICK_VOLUME_RATIO,
            "atr_percentile": atr_percentile / 100.0,
            "vwap_deviation": vwap_deviation,
        }


__all__ = [
    "ExpandedFeatureExtractor",
    "compute_directional_efficiency",
    "compute_rsi_zscore",
    "compute_tick_volume_ratio",
    "compute_vwap_deviation",
]
