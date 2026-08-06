from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.indicators.trend import ExponentialMovingAverage, SimpleMovingAverage
from core.interfaces.types import Bar, Symbol, Timeframe


def _bar(close: float, index: int = 0) -> Bar:
    return Bar(
        symbol=Symbol(name="EURUSD"),
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC).replace(minute=index % 60),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0,
    )


def test_sma_returns_none_until_warmed_up_then_averages() -> None:
    sma = SimpleMovingAverage(period=3)

    assert sma.update(_bar(1)) is None
    assert sma.update(_bar(2)) is None
    assert sma.update(_bar(3)) == pytest.approx(2.0)
    assert sma.update(_bar(4)) == pytest.approx(3.0)
    assert sma.update(_bar(5)) == pytest.approx(4.0)


def test_sma_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        SimpleMovingAverage(period=0)


def test_ema_seeds_with_first_close_then_smooths() -> None:
    ema = ExponentialMovingAverage(period=3)

    assert ema.update(_bar(1)) == pytest.approx(1.0)
    assert ema.update(_bar(2)) == pytest.approx(1.5)
    assert ema.update(_bar(3)) == pytest.approx(2.25)
    assert ema.update(_bar(4)) == pytest.approx(3.125)
