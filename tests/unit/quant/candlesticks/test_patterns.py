from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from analytics.hit_rate_store import HistoricalHitRateStore
from core.interfaces.types import Bar, Direction, MarketContext, Symbol, Timeframe
from quant.candlesticks.patterns import EngulfingPatternModule

_SYMBOL = Symbol(name="EURUSD")


def _context(ohlc: list[tuple[float, float, float, float]]) -> MarketContext:
    bars = tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=o,
            high=max(o, h, low, c),
            low=min(o, h, low, c),
            close=c,
            volume=0.0,
        )
        for i, (o, h, low, c) in enumerate(ohlc)
    )
    return MarketContext(symbol=_SYMBOL, bars=bars)


def test_bullish_engulfing_emits_long_evidence() -> None:
    module = EngulfingPatternModule()
    # Bearish candle (1.10 -> 1.08), then a bullish candle whose body fully
    # contains it (1.07 -> 1.12).
    bars = [(1.10, 1.10, 1.08, 1.08), (1.07, 1.12, 1.07, 1.12)]

    evidence = module.analyze(_context(bars))

    assert len(evidence) == 1
    item = evidence[0]
    assert item.source_module == "engulfing_pattern"
    assert item.direction == Direction.LONG
    assert item.rationale["size_ratio"] == pytest.approx(2.5)
    assert item.confidence == pytest.approx(1.0)


def test_bearish_engulfing_emits_short_evidence() -> None:
    module = EngulfingPatternModule()
    # Bullish candle (1.08 -> 1.10), then a bearish candle whose body fully
    # contains it (1.12 -> 1.07).
    bars = [(1.08, 1.10, 1.08, 1.10), (1.12, 1.12, 1.07, 1.07)]

    evidence = module.analyze(_context(bars))

    assert len(evidence) == 1
    assert evidence[0].direction == Direction.SHORT


def test_partial_engulfment_yields_partial_confidence() -> None:
    module = EngulfingPatternModule()
    bars = [(1.10, 1.10, 1.08, 1.08), (1.075, 1.105, 1.075, 1.105)]

    evidence = module.analyze(_context(bars))

    assert len(evidence) == 1
    assert evidence[0].confidence == pytest.approx(0.5)


def test_non_engulfing_body_emits_no_evidence() -> None:
    module = EngulfingPatternModule()
    # Current body sits inside the previous body -- not an engulfment.
    bars = [(1.10, 1.10, 1.05, 1.05), (1.06, 1.08, 1.06, 1.08)]

    assert module.analyze(_context(bars)) == []


def test_same_direction_candles_do_not_qualify() -> None:
    module = EngulfingPatternModule()
    bars = [(1.05, 1.09, 1.05, 1.09), (1.04, 1.12, 1.04, 1.12)]

    assert module.analyze(_context(bars)) == []


def test_fewer_than_two_bars_emits_no_evidence() -> None:
    module = EngulfingPatternModule()

    assert module.analyze(_context([(1.0, 1.0, 1.0, 1.0)])) == []


def test_zero_size_body_emits_no_evidence() -> None:
    module = EngulfingPatternModule()
    # Previous candle is a doji (open == close): zero-size body, can't engulf.
    bars = [(1.10, 1.10, 1.10, 1.10), (1.05, 1.15, 1.05, 1.15)]

    assert module.analyze(_context(bars)) == []


def test_hit_rate_store_overrides_geometric_confidence_once_enough_history() -> None:
    store = HistoricalHitRateStore(min_samples=3)
    module = EngulfingPatternModule(hit_rate_store=store)
    bars = [(1.10, 1.10, 1.08, 1.08), (1.07, 1.12, 1.07, 1.12)]

    # Not enough history yet -> falls back to the original geometric behavior.
    evidence = module.analyze(_context(bars))
    assert evidence[0].confidence == pytest.approx(1.0)
    assert evidence[0].rationale["confidence_source"] == "geometric"

    # Once the store has enough samples, its empirical hit rate takes over.
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)
    store.record_outcome("engulfing_pattern", "EURUSD", won=True)
    store.record_outcome("engulfing_pattern", "EURUSD", won=False)

    evidence = module.analyze(_context(bars))
    assert evidence[0].confidence == pytest.approx(2 / 3)
    assert evidence[0].rationale["confidence_source"] == "historical_hit_rate"
    assert evidence[0].supporting_data["geometric_confidence"] == pytest.approx(1.0)


def test_no_hit_rate_store_preserves_original_geometric_behavior() -> None:
    module = EngulfingPatternModule()
    bars = [(1.10, 1.10, 1.08, 1.08), (1.07, 1.12, 1.07, 1.12)]

    evidence = module.analyze(_context(bars))

    assert evidence[0].confidence == pytest.approx(1.0)
    assert evidence[0].rationale["confidence_source"] == "geometric"
