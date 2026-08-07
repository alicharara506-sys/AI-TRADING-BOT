from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.multi_timeframe.alignment import HigherTimeframeAlignmentModule

_SYMBOL = Symbol(name="EURUSD")


def _bar(o: float, h: float, low: float, c: float, i: int, timeframe: Timeframe) -> Bar:
    return Bar(
        symbol=_SYMBOL,
        timeframe=timeframe,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=1.0,
    )


def _trending_bars(count: int, timeframe: Timeframe) -> tuple[Bar, ...]:
    return tuple(
        _bar(9.5 + i, 10.0 + i, 9.0 + i, 9.7 + i, i, timeframe) for i in range(count)
    )


def _ranging_bars(count: int, timeframe: Timeframe) -> tuple[Bar, ...]:
    return tuple(
        _bar(10.0, 10.2, 9.8, 10.0 + (0.05 if i % 2 == 0 else -0.05), i, timeframe)
        for i in range(count)
    )


def _primary_bars() -> tuple[Bar, ...]:
    return tuple(_bar(1.10, 1.11, 1.09, 1.10, i, Timeframe.M15) for i in range(5))


def test_rejects_invalid_construction_parameters() -> None:
    with pytest.raises(ValueError):
        HigherTimeframeAlignmentModule(timeframe=Timeframe.H4, adx_period=1)
    with pytest.raises(ValueError):
        HigherTimeframeAlignmentModule(timeframe=Timeframe.H4, trend_threshold=0.0)
    with pytest.raises(ValueError):
        HigherTimeframeAlignmentModule(timeframe=Timeframe.H4, trend_threshold=100.0)


def test_emits_long_evidence_when_the_higher_timeframe_is_trending_up() -> None:
    module = HigherTimeframeAlignmentModule(timeframe=Timeframe.H4, adx_period=5)
    context = MarketContext(
        symbol=_SYMBOL,
        bars=_primary_bars(),
        higher_timeframe_bars={Timeframe.H4: _trending_bars(30, Timeframe.H4)},
    )

    evidence = module.analyze(context)

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.LONG
    assert evidence[0].rationale["timeframe"] == "H4"


def test_emits_no_evidence_when_the_higher_timeframe_is_ranging() -> None:
    module = HigherTimeframeAlignmentModule(timeframe=Timeframe.H4, adx_period=5)
    context = MarketContext(
        symbol=_SYMBOL,
        bars=_primary_bars(),
        higher_timeframe_bars={Timeframe.H4: _ranging_bars(30, Timeframe.H4)},
    )

    assert module.analyze(context) == []


def test_emits_no_evidence_when_the_configured_timeframe_is_missing() -> None:
    module = HigherTimeframeAlignmentModule(timeframe=Timeframe.H4, adx_period=5)
    context = MarketContext(
        symbol=_SYMBOL,
        bars=_primary_bars(),
        higher_timeframe_bars={Timeframe.D1: _trending_bars(30, Timeframe.D1)},
    )

    assert module.analyze(context) == []


def test_emits_no_evidence_with_no_higher_timeframe_data_at_all() -> None:
    # The default, backward-compatible case: a caller that never populated
    # higher_timeframe_bars at all (every pre-Phase-4 MarketContext).
    module = HigherTimeframeAlignmentModule(timeframe=Timeframe.H4, adx_period=5)
    context = MarketContext(symbol=_SYMBOL, bars=_primary_bars())

    assert module.analyze(context) == []
