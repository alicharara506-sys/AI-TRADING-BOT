from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from quant.multi_timeframe.alignment import HigherTimeframeAlignmentModule
from quant.technical_analysis.momentum import AdxTrendModule

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


def _trending_up(count: int, timeframe: Timeframe) -> tuple[Bar, ...]:
    return tuple(_bar(9.5 + i, 10.0 + i, 9.0 + i, 9.7 + i, i, timeframe) for i in range(count))


def _trending_down(count: int, timeframe: Timeframe) -> tuple[Bar, ...]:
    return tuple(
        _bar(30.0 - i, 30.5 - i, 29.5 - i, 29.8 - i, i, timeframe) for i in range(count)
    )


def _engine() -> SignalEngine:
    engine = SignalEngine(SignalFusion(threshold=0.5))
    engine.register_module(AdxTrendModule(period=5, trend_threshold=20.0))
    engine.register_module(
        HigherTimeframeAlignmentModule(timeframe=Timeframe.H4, adx_period=5, trend_threshold=20.0)
    )
    return engine


def test_higher_timeframe_alignment_reinforces_an_agreeing_primary_signal() -> None:
    """HigherTimeframeAlignmentModule registers into the exact same
    SignalEngine/SignalFusion every earlier phase's modules use, with zero
    changes to core/signal/fusion.py. When the M15 trend (AdxTrendModule)
    and the H4 trend (HigherTimeframeAlignmentModule) agree, both votes
    reinforce each other into a strongly confident consensus.
    """
    engine = _engine()
    context = MarketContext(
        symbol=_SYMBOL,
        bars=_trending_up(30, Timeframe.M15),
        higher_timeframe_bars={Timeframe.H4: _trending_up(30, Timeframe.H4)},
    )

    signal = engine.evaluate(context)

    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.combined_confidence > 0.9
    contributing = {item.source_module for item in signal.evidence}
    assert contributing == {"adx_trend", "higher_timeframe_alignment"}


def test_higher_timeframe_alignment_is_one_more_vote_not_a_veto() -> None:
    """A lower-timeframe signal against the higher-timeframe trend isn't
    silently discarded (a separate parallel gate/veto would do that) --
    it's weighed against it like any other disagreeing Evidence, through
    the exact same log-odds fusion every other module already goes
    through. Two maximally-confident, opposite-direction votes settle
    exactly at the fusion's neutral point.
    """
    engine = _engine()
    context = MarketContext(
        symbol=_SYMBOL,
        bars=_trending_up(30, Timeframe.M15),
        higher_timeframe_bars={Timeframe.H4: _trending_down(30, Timeframe.H4)},
    )

    signal = engine.evaluate(context)

    assert signal is not None
    assert signal.combined_confidence == pytest.approx(0.5)
    directions = {item.source_module: item.direction for item in signal.evidence}
    assert directions["adx_trend"] == Direction.LONG
    assert directions["higher_timeframe_alignment"] == Direction.SHORT
