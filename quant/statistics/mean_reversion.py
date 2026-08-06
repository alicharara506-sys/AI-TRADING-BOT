from __future__ import annotations

import numpy as np
from statsmodels.tsa.stattools import adfuller

from core.interfaces.types import Direction, Evidence, MarketContext


class AdfMeanReversionModule:
    """Mean-reversion Evidence, gated by an Augmented Dickey-Fuller stationarity
    test on the recent close-price window. A directional distance-from-mean
    signal is only trusted when the ADF test actually rejects a unit root --
    otherwise the series may be trending rather than mean-reverting, and this
    module emits no Evidence at all rather than a low-confidence guess.
    """

    name = "adf_mean_reversion"

    def __init__(
        self,
        *,
        window: int = 30,
        significance: float = 0.05,
        z_score_scale: float = 2.0,
        min_z_score: float = 0.5,
    ) -> None:
        if window < 8:
            raise ValueError("window must be >= 8 for a meaningful ADF test")
        if not 0.0 < significance < 1.0:
            raise ValueError("significance must be in (0, 1)")
        if z_score_scale <= 0:
            raise ValueError("z_score_scale must be > 0")
        self._window = window
        self._significance = significance
        self._z_score_scale = z_score_scale
        self._min_z_score = min_z_score

    def analyze(self, context: MarketContext) -> list[Evidence]:
        if len(context.bars) < self._window:
            return []

        closes = [bar.close for bar in context.bars[-self._window :]]
        prices = np.asarray(closes, dtype=float)
        mean = float(prices.mean())
        std = float(prices.std(ddof=1))
        if std < 1e-12:
            # Effectively flat: floating-point rounding means a truly constant
            # price series rarely produces an exact 0.0 std (summing/dividing
            # identical floats still accumulates rounding error), so this must
            # be a tolerance check, not an exact-equality one.
            return []

        _, p_value, *_ = adfuller(prices, autolag="AIC")
        p_value = float(p_value)
        if p_value > self._significance:
            return []  # cannot reject a unit root: likely trending, not mean-reverting

        current = float(prices[-1])
        z_score = (current - mean) / std
        if abs(z_score) < self._min_z_score:
            return []

        stationarity_confidence = 1.0 - (p_value / self._significance)
        distance_confidence = min(abs(z_score) / self._z_score_scale, 1.0)
        confidence = stationarity_confidence * distance_confidence
        if confidence <= 0.0:
            return []

        # Above its own mean in a stationary series should revert down (SHORT);
        # below its mean should revert up (LONG).
        direction = Direction.SHORT if z_score > 0 else Direction.LONG

        evidence = Evidence(
            source_module=self.name,
            direction=direction,
            confidence=confidence,
            rationale={
                "adf_p_value": p_value,
                "z_score": z_score,
                "window": self._window,
            },
            supporting_data={"mean": mean, "std": std, "current": current},
        )
        return [evidence]


__all__ = ["AdfMeanReversionModule"]
