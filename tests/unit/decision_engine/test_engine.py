from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.interfaces.types import (
    Bar,
    Direction,
    Evidence,
    MarketContext,
    Symbol,
    Timeframe,
    TradeSignal,
)
from core.risk.sizing import FixedVolumeSizingModel
from decision_engine.engine import DecisionEngine

_SYMBOL = Symbol(name="EURUSD")


def _bars(count: int = 20) -> tuple[Bar, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=start + timedelta(minutes=i),
            open=1.10 + i * 0.001,
            high=1.10 + i * 0.001 + 0.002,
            low=1.10 + i * 0.001 - 0.002,
            close=1.10 + i * 0.001,
            volume=0.0,
        )
        for i in range(count)
    )


def _signal(direction: Direction, confidence: float = 0.8, module: str = "m1") -> TradeSignal:
    return TradeSignal(
        symbol=_SYMBOL,
        direction=direction,
        combined_confidence=confidence,
        threshold=0.6,
        evidence=(Evidence(source_module=module, direction=direction, confidence=confidence),),
    )


class _FakeStore:
    def __init__(self, counts: dict[tuple[str, str], int]) -> None:
        self._counts = counts

    def hit_rate(self, module_name: str, symbol: str) -> float | None:
        return 0.6

    def sample_count(self, module_name: str, symbol: str) -> int:
        return self._counts.get((module_name, symbol), 0)


def test_rejects_invalid_construction_parameters() -> None:
    sizing = FixedVolumeSizingModel(0.1)
    with pytest.raises(ValueError, match="atr_period"):
        DecisionEngine(sizing, atr_period=1)
    with pytest.raises(ValueError, match="atr_multiple"):
        DecisionEngine(sizing, atr_multiple=0.0)
    with pytest.raises(ValueError, match="risk_reward_ratio"):
        DecisionEngine(sizing, risk_reward_ratio=0.0)
    with pytest.raises(ValueError, match="low_uncertainty_samples"):
        DecisionEngine(sizing, low_uncertainty_samples=5, medium_uncertainty_samples=10)


def test_confidence_and_probability_of_success_surface_the_signals_own_value() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1))
    signal = _signal(Direction.LONG, confidence=0.83)
    context = MarketContext(symbol=_SYMBOL, bars=_bars())

    report = engine.decide(signal, context, equity=10_000.0)

    assert report.confidence == pytest.approx(0.83)
    assert report.probability_of_success == pytest.approx(0.83)
    assert report.signal is signal


def test_position_size_comes_from_the_injected_sizing_model() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.25))
    context = MarketContext(symbol=_SYMBOL, bars=_bars())

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.recommended_position_size == pytest.approx(0.25)


def test_long_stop_loss_is_below_entry_and_take_profit_above() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), atr_multiple=2.0, risk_reward_ratio=1.5)
    context = MarketContext(symbol=_SYMBOL, bars=_bars())
    entry_price = context.bars[-1].close

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.recommended_stop_loss is not None
    assert report.recommended_take_profit is not None
    assert report.recommended_stop_loss < entry_price
    assert report.recommended_take_profit > entry_price


def test_short_stop_loss_is_above_entry_and_take_profit_below() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), atr_multiple=2.0, risk_reward_ratio=1.5)
    context = MarketContext(symbol=_SYMBOL, bars=_bars())
    entry_price = context.bars[-1].close

    report = engine.decide(_signal(Direction.SHORT), context, equity=10_000.0)

    assert report.recommended_stop_loss is not None
    assert report.recommended_take_profit is not None
    assert report.recommended_stop_loss > entry_price
    assert report.recommended_take_profit < entry_price


def test_take_profit_distance_matches_the_configured_risk_reward_ratio() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), atr_multiple=2.0, risk_reward_ratio=1.5)
    context = MarketContext(symbol=_SYMBOL, bars=_bars())
    entry_price = context.bars[-1].close

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.recommended_stop_loss is not None
    assert report.recommended_take_profit is not None
    risk = entry_price - report.recommended_stop_loss
    reward = report.recommended_take_profit - entry_price
    assert reward / risk == pytest.approx(1.5)


def test_insufficient_bars_yields_no_stop_loss_or_take_profit_rather_than_a_guess() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), atr_period=14)
    context = MarketContext(symbol=_SYMBOL, bars=_bars(3))

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.atr is None
    assert report.recommended_stop_loss is None
    assert report.recommended_take_profit is None


def test_mismatched_symbol_raises() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1))
    context = MarketContext(symbol=Symbol(name="GBPUSD"), bars=_bars())

    with pytest.raises(ValueError, match="EURUSD.*GBPUSD"):
        engine.decide(_signal(Direction.LONG), context, equity=10_000.0)


def test_uncertainty_is_high_with_no_reliability_store() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1))
    context = MarketContext(symbol=_SYMBOL, bars=_bars())

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.uncertainty == "high"


@pytest.mark.parametrize(
    "sample_count,expected",
    [(50, "low"), (15, "medium"), (2, "high"), (0, "high")],
)
def test_uncertainty_buckets_by_weakest_contributing_modules_sample_count(
    sample_count: int, expected: str
) -> None:
    engine = DecisionEngine(
        FixedVolumeSizingModel(0.1),
        reliability_store=_FakeStore({("m1", "EURUSD"): sample_count}),
    )
    context = MarketContext(symbol=_SYMBOL, bars=_bars())

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.uncertainty == expected


def test_uncertainty_reflects_the_weakest_of_multiple_contributing_modules() -> None:
    signal = TradeSignal(
        symbol=_SYMBOL,
        direction=Direction.LONG,
        combined_confidence=0.8,
        threshold=0.6,
        evidence=(
            Evidence(source_module="strong", direction=Direction.LONG, confidence=0.8),
            Evidence(source_module="weak", direction=Direction.LONG, confidence=0.7),
        ),
    )
    engine = DecisionEngine(
        FixedVolumeSizingModel(0.1),
        reliability_store=_FakeStore({("strong", "EURUSD"): 100, ("weak", "EURUSD"): 2}),
    )
    context = MarketContext(symbol=_SYMBOL, bars=_bars())

    report = engine.decide(signal, context, equity=10_000.0)

    assert report.uncertainty == "high"  # gated by the weakest module, not the strongest
