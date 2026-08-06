from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.statistics.mean_reversion import AdfMeanReversionModule

_SYMBOL = Symbol(name="EURUSD")


def _context(closes: list[float]) -> MarketContext:
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=0.0,
        )
        for i, close in enumerate(closes)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


def _ar1_series(*, n: int, mu: float, phi: float, noise_std: float, seed: int) -> list[float]:
    """A genuinely stationary AR(1) process: x[t] = mu + phi*(x[t-1]-mu) + noise.
    phi < 1 guarantees mean reversion; this is real ADF-testable synthetic data,
    not a hand-picked sequence."""
    rng = np.random.default_rng(seed)
    x = np.empty(n)
    x[0] = mu
    for t in range(1, n):
        x[t] = mu + phi * (x[t - 1] - mu) + rng.normal(0, noise_std)
    return list(x)


def _trending_series(
    *, n: int, start: float, drift: float, noise_std: float, seed: int
) -> list[float]:
    """A random walk with drift: non-stationary by construction (integrated of
    order 1), so ADF should fail to reject its unit root."""
    rng = np.random.default_rng(seed)
    return list(start + np.cumsum(rng.normal(drift, noise_std, n)))


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        AdfMeanReversionModule(window=4)
    with pytest.raises(ValueError):
        AdfMeanReversionModule(significance=1.5)
    with pytest.raises(ValueError):
        AdfMeanReversionModule(z_score_scale=0.0)


def test_stationary_series_emits_evidence_with_correct_direction() -> None:
    # Verified empirically (see the commit this test was introduced in): this
    # exact fixture gives ADF p_value ~= 0.022 and z_score ~= +1.98.
    closes = _ar1_series(n=60, mu=1.10, phi=0.5, noise_std=0.001, seed=7)
    module = AdfMeanReversionModule(window=30)

    evidence = module.analyze(_context(closes))

    assert len(evidence) == 1
    item = evidence[0]
    assert item.source_module == "adf_mean_reversion"
    # Price sits above its own (stationary) mean -> expect reversion down.
    assert item.direction == Direction.SHORT
    assert 0.0 < item.confidence <= 1.0
    assert item.rationale["adf_p_value"] < 0.05


def test_trending_series_emits_no_evidence() -> None:
    closes = _trending_series(n=60, start=1.10, drift=0.0015, noise_std=0.001, seed=7)
    module = AdfMeanReversionModule(window=30)

    assert module.analyze(_context(closes)) == []


def test_window_shorter_than_configured_emits_no_evidence() -> None:
    closes = _ar1_series(n=20, mu=1.10, phi=0.5, noise_std=0.001, seed=7)
    module = AdfMeanReversionModule(window=30)

    assert module.analyze(_context(closes)) == []


def test_flat_series_with_zero_variance_emits_no_evidence() -> None:
    closes = [1.10] * 40
    module = AdfMeanReversionModule(window=30)

    assert module.analyze(_context(closes)) == []
