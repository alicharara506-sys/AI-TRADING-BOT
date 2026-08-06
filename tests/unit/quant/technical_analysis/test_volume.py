from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.technical_analysis.volume import OnBalanceVolumeModule

_SYMBOL = Symbol(name="EURUSD")


def _context(closes_volumes: list[tuple[float, float]]) -> MarketContext:
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=volume,
        )
        for i, (close, volume) in enumerate(closes_volumes)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


# Verified empirically: price rises, and volume is concentrated on the up-ticks
# -> OBV rises too (confirmation).
_CONFIRM_UP = [
    (1.00, 0), (1.01, 100), (1.02, 110), (1.03, 120), (1.04, 90), (1.05, 130),
    (1.06, 140), (1.07, 100), (1.08, 120), (1.09, 150), (1.10, 160),
]
# Verified empirically: price rises overall, but volume is concentrated on the
# down-ticks -> OBV falls (divergence).
_DIVERGE_UP = [
    (1.10, 0), (1.09, 200), (1.08, 180), (1.11, 10), (1.07, 190), (1.12, 5),
    (1.06, 210), (1.13, 5), (1.05, 220), (1.14, 5), (1.15, 5),
]
_CONFIRM_DOWN = [
    (1.10, 0), (1.09, 100), (1.08, 110), (1.07, 120), (1.06, 90), (1.05, 130),
    (1.04, 140), (1.03, 100), (1.02, 120), (1.01, 150), (1.00, 160),
]


def test_rejects_invalid_lookback() -> None:
    with pytest.raises(ValueError):
        OnBalanceVolumeModule(lookback=1)


def test_confirmation_on_rising_price_and_obv() -> None:
    module = OnBalanceVolumeModule(lookback=10)

    evidence = module.analyze(_context(_CONFIRM_UP))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG
    assert evidence[0].rationale["event"] == "obv_confirms_trend"


def test_confirmation_on_falling_price_and_obv() -> None:
    module = OnBalanceVolumeModule(lookback=10)

    evidence = module.analyze(_context(_CONFIRM_DOWN))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].rationale["event"] == "obv_confirms_trend"


def test_divergence_between_price_and_obv() -> None:
    module = OnBalanceVolumeModule(lookback=10)

    evidence = module.analyze(_context(_DIVERGE_UP))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT
    assert evidence[0].rationale["event"] == "obv_diverges_from_price"


def test_too_few_bars_emits_no_evidence() -> None:
    module = OnBalanceVolumeModule(lookback=10)

    assert module.analyze(_context(_CONFIRM_UP[:5])) == []
