from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np
from statsmodels.tsa.stattools import adfuller

from core.interfaces.types import Bar
from quant.technical_analysis.momentum import compute_adx

DirectionalRegime = Literal["trend_up", "trend_down", "mean_revert"]


def compute_directional_regime(
    bars: Sequence[Bar],
    *,
    adx_period: int = 14,
    trend_threshold: float = 25.0,
    mean_reversion_window: int = 30,
    significance: float = 0.05,
) -> DirectionalRegime | None:
    """A 3-state TREND_UP / TREND_DOWN / MEAN_REVERT read, composed entirely
    from statistical tests this platform already trusts elsewhere rather
    than a new ATR-percentile-plus-consecutive-HH/HL heuristic: ADX/DI
    (quant.technical_analysis.momentum.compute_adx, the same trend-strength
    -and-direction test AdxTrendModule votes on) decides TREND_UP/DOWN, and
    the Augmented Dickey-Fuller stationarity test (the same gate
    AdfMeanReversionModule already requires before it will call anything
    mean-reverting) decides MEAN_REVERT. Matches compute_volatility_regime's
    own stated principle next to it in this package: no fabricated absolute
    regime label without a real statistical test behind it, so this returns
    None -- not a guessed third bucket -- whenever price is neither
    ADX-confirmed trending nor ADF-confirmed mean-reverting (the "unclear"
    case).

    A caller wanting a "high volatility" read as well should combine this
    with compute_volatility_regime -- volatility and trend/mean-reversion
    are orthogonal axes here, exactly as the ATLAS reference tracker treats
    HIGH_VOL as a risk-sizing overlay independent of trend direction, not a
    fourth value competing with the other three.
    """
    if mean_reversion_window < 8:
        raise ValueError("mean_reversion_window must be >= 8 for a meaningful ADF test")
    if not 0.0 < significance < 1.0:
        raise ValueError("significance must be in (0, 1)")

    adx_result = compute_adx(bars, period=adx_period)
    if adx_result is not None:
        plus_di, minus_di, adx = adx_result
        if adx >= trend_threshold and plus_di != minus_di:
            return "trend_up" if plus_di > minus_di else "trend_down"

    if len(bars) < mean_reversion_window:
        return None
    closes = np.asarray([bar.close for bar in bars[-mean_reversion_window:]], dtype=float)
    if closes.std(ddof=1) < 1e-12:
        return None
    _, p_value, *_ = adfuller(closes, autolag="AIC")
    if float(p_value) <= significance:
        return "mean_revert"
    return None


__all__ = ["DirectionalRegime", "compute_directional_regime"]
