from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Symbol, Timeframe
from quant.statistics.correlation import compute_correlation_matrix

_EURUSD = Symbol(name="EURUSD")
_GBPUSD = Symbol(name="GBPUSD")


def _bars(symbol: Symbol, closes: list[float]) -> list[Bar]:
    return [
        Bar(
            symbol=symbol,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1.0,
        )
        for i, c in enumerate(closes)
    ]


def test_rejects_fewer_than_two_symbols() -> None:
    with pytest.raises(ValueError):
        compute_correlation_matrix({"EURUSD": _bars(_EURUSD, [1.0] * 30)})


def test_rejects_invalid_min_samples() -> None:
    with pytest.raises(ValueError):
        compute_correlation_matrix(
            {"A": _bars(_EURUSD, [1.0] * 30), "B": _bars(_GBPUSD, [1.0] * 30)}, min_samples=1
        )


def test_perfectly_correlated_symbols_score_one() -> None:
    base = [1.0 + 0.001 * i for i in range(30)]
    scaled = [2.0 * c for c in base]

    matrix = compute_correlation_matrix(
        {"A": _bars(_EURUSD, base), "B": _bars(_GBPUSD, scaled)}, min_samples=10
    )

    assert matrix is not None
    assert matrix["A"]["A"] == pytest.approx(1.0)
    assert matrix["A"]["B"] == pytest.approx(1.0)
    assert matrix["B"]["A"] == pytest.approx(1.0)


def test_perfectly_anticorrelated_symbols_score_minus_one() -> None:
    # B's return at every step is the exact negative of A's -- the only way
    # to guarantee Pearson(-1) exactly, since deriving B from a price-domain
    # mirror of A (e.g. 2.0 - price) does not actually invert the *returns*.
    step_returns = [0.001 * ((i % 5) - 2) for i in range(29)]
    base = [1.0]
    for r in step_returns:
        base.append(base[-1] * (1 + r))
    inverted = [1.0]
    for r in step_returns:
        inverted.append(inverted[-1] * (1 - r))

    matrix = compute_correlation_matrix(
        {"A": _bars(_EURUSD, base), "B": _bars(_GBPUSD, inverted)}, min_samples=10
    )

    assert matrix is not None
    assert matrix["A"]["B"] == pytest.approx(-1.0)


def test_returns_none_with_insufficient_shared_history() -> None:
    matrix = compute_correlation_matrix(
        {"A": _bars(_EURUSD, [1.0] * 5), "B": _bars(_GBPUSD, [1.0] * 5)}, min_samples=20
    )

    assert matrix is None


def test_returns_none_with_no_overlapping_timestamps() -> None:
    a = [
        Bar(
            symbol=_EURUSD,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        for i in range(30)
    ]
    b = [
        Bar(
            symbol=_GBPUSD,
            timeframe=Timeframe.M1,
            timestamp=datetime(2027, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        for i in range(30)
    ]

    matrix = compute_correlation_matrix({"A": a, "B": b}, min_samples=5)

    assert matrix is None
