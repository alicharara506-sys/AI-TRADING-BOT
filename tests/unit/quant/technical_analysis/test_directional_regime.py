from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from core.interfaces.types import Bar, Symbol, Timeframe
from quant.technical_analysis.directional_regime import compute_directional_regime

_SYMBOL = Symbol(name="EURUSD")


def _bars(ohlc: list[tuple[float, float, float, float]]) -> list[Bar]:
    return [
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=1.0,
        )
        for i, (o, h, low, c) in enumerate(ohlc)
    ]


def _trending_bars(count: int, *, up: bool = True) -> list[Bar]:
    step = 1.0 if up else -1.0
    ohlc = [
        (9.5 + step * i, 10.0 + step * i, 9.0 + step * i, 9.7 + step * i) for i in range(count)
    ]
    return _bars(ohlc)


def _ranging_bars(count: int) -> list[Bar]:
    ohlc = [(9.9, 10.1, 9.9, 10.0) for _ in range(count)]
    return _bars(ohlc)


def _flat_close_bars_with_ar1_closes(
    *, n: int, mu: float, phi: float, noise_std: float, seed: int
) -> list[Bar]:
    """A genuinely stationary AR(1) close-price series with no directional
    drift in the OHLC range, so ADX stays weak (not trending) while ADF can
    still reject a unit root on the closes -- the same synthetic-data
    approach quant/statistics/mean_reversion's own tests already use."""
    rng = np.random.default_rng(seed)
    closes = np.empty(n)
    closes[0] = mu
    for t in range(1, n):
        closes[t] = mu + phi * (closes[t - 1] - mu) + rng.normal(0, noise_std)
    ohlc = [(float(c), float(c) + 0.05, float(c) - 0.05, float(c)) for c in closes]
    return _bars(ohlc)


def test_rejects_invalid_construction_parameters() -> None:
    bars = _ranging_bars(40)
    with pytest.raises(ValueError):
        compute_directional_regime(bars, mean_reversion_window=4)
    with pytest.raises(ValueError):
        compute_directional_regime(bars, significance=0.0)


def test_returns_trend_up_in_a_clean_uptrend() -> None:
    bars = _trending_bars(30, up=True)

    assert compute_directional_regime(bars, adx_period=5) == "trend_up"


def test_returns_trend_down_in_a_clean_downtrend() -> None:
    bars = _trending_bars(30, up=False)

    assert compute_directional_regime(bars, adx_period=5) == "trend_down"


def test_returns_mean_revert_for_a_stationary_ar1_series() -> None:
    bars = _flat_close_bars_with_ar1_closes(n=40, mu=10.0, phi=0.3, noise_std=0.5, seed=7)

    regime = compute_directional_regime(bars, adx_period=5, mean_reversion_window=40)

    assert regime == "mean_revert"


def test_returns_none_for_a_flat_constant_series() -> None:
    bars = _ranging_bars(40)

    assert compute_directional_regime(bars, adx_period=5, mean_reversion_window=30) is None


def test_returns_none_with_insufficient_history() -> None:
    bars = _ranging_bars(10)

    assert compute_directional_regime(bars, adx_period=14, mean_reversion_window=30) is None
