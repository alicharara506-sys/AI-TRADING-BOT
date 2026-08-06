from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.indicators.momentum import RelativeStrengthIndex
from core.interfaces.types import Bar, Symbol, Timeframe


def _bar(close: float) -> Bar:
    return Bar(
        symbol=Symbol(name="EURUSD"),
        timeframe=Timeframe.M1,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=0.0,
    )


def test_rsi_warms_up_then_matches_wilder_formula() -> None:
    rsi = RelativeStrengthIndex(period=2)

    assert rsi.update(_bar(1)) is None
    assert rsi.update(_bar(2)) is None
    assert rsi.update(_bar(1)) == pytest.approx(50.0)
    assert rsi.update(_bar(2)) == pytest.approx(75.0)
    assert rsi.update(_bar(3)) == pytest.approx(87.5)


def test_rsi_rejects_invalid_period() -> None:
    with pytest.raises(ValueError):
        RelativeStrengthIndex(period=0)
