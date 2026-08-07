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
from core.risk.sizing import FixedVolumeSizingModel, RiskPercentSizingModel
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


# -- Phase 5 schema expansion --------------------------------------------------


def _trending_bars(count: int, *, up: bool) -> tuple[Bar, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    sign = 1.0 if up else -1.0
    return tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=start + timedelta(minutes=i),
            open=9.5 + sign * i,
            high=10.0 + sign * i,
            low=9.0 + sign * i,
            close=9.7 + sign * i,
            volume=0.0,
        )
        for i in range(count)
    )


def _ranging_bars(count: int) -> tuple[Bar, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=start + timedelta(minutes=i),
            open=10.0,
            high=10.2,
            low=9.8,
            close=10.0 + (0.05 if i % 2 == 0 else -0.05),
            volume=0.0,
        )
        for i in range(count)
    )


def _range_spike_bars(ranges: list[float]) -> tuple[Bar, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    price = 100.0
    for i, r in enumerate(ranges):
        bars.append(
            Bar(
                symbol=_SYMBOL,
                timeframe=Timeframe.M1,
                timestamp=start + timedelta(minutes=i),
                open=price,
                high=price + r / 2,
                low=price - r / 2,
                close=price,
                volume=0.0,
            )
        )
    return tuple(bars)


_SWING_PRICES = [
    1.10, 1.07, 1.04, 1.00, 1.02, 1.05, 1.08, 1.11, 1.14, 1.17, 1.20, 1.18, 1.16,
]


def _swing_bars() -> tuple[Bar, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        Bar(
            symbol=_SYMBOL,
            timeframe=Timeframe.M1,
            timestamp=start + timedelta(minutes=i),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=0.0,
        )
        for i, price in enumerate(_SWING_PRICES)
    )


def test_new_optional_fields_default_to_none_with_insufficient_bars() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1))
    context = MarketContext(symbol=_SYMBOL, bars=_bars(3))

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.take_profit_2 is None
    assert report.risk_reward_ratio is None
    assert report.trend_tag is None
    assert report.volatility_tag is None
    assert report.invalidation_level is None


def test_take_profit_2_uses_the_configured_second_risk_reward_ratio() -> None:
    engine = DecisionEngine(
        FixedVolumeSizingModel(0.1),
        atr_multiple=2.0,
        risk_reward_ratio=1.5,
        risk_reward_ratio_2=3.0,
    )
    context = MarketContext(symbol=_SYMBOL, bars=_bars())
    entry_price = context.bars[-1].close

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.recommended_stop_loss is not None
    assert report.take_profit_2 is not None
    risk = entry_price - report.recommended_stop_loss
    reward2 = report.take_profit_2 - entry_price
    assert reward2 / risk == pytest.approx(3.0)
    assert report.risk_reward_ratio == pytest.approx(1.5)


def test_trend_tag_reflects_a_strong_uptrend() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), adx_period=5, trend_threshold=20.0)
    context = MarketContext(symbol=_SYMBOL, bars=_trending_bars(30, up=True))

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.trend_tag == "uptrend"


def test_trend_tag_reflects_a_strong_downtrend() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), adx_period=5, trend_threshold=20.0)
    context = MarketContext(symbol=_SYMBOL, bars=_trending_bars(30, up=False))

    report = engine.decide(_signal(Direction.SHORT), context, equity=10_000.0)

    assert report.trend_tag == "downtrend"


def test_trend_tag_is_ranging_in_a_choppy_market() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), adx_period=5, trend_threshold=25.0)
    context = MarketContext(symbol=_SYMBOL, bars=_ranging_bars(30))

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.trend_tag == "ranging"


def test_volatility_tag_reflects_a_real_spike() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), atr_period=2, volatility_lookback=15)
    ranges = [1.0] * 20 + [10.0]
    context = MarketContext(symbol=_SYMBOL, bars=_range_spike_bars(ranges))

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.volatility_tag == "high"


def test_invalidation_level_uses_the_nearest_confirmed_swing() -> None:
    engine = DecisionEngine(FixedVolumeSizingModel(0.1), structure_swing_arm=2)
    context = MarketContext(symbol=_SYMBOL, bars=_swing_bars())

    long_report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)
    short_report = engine.decide(_signal(Direction.SHORT), context, equity=10_000.0)

    assert long_report.invalidation_level == pytest.approx(1.00)
    assert short_report.invalidation_level == pytest.approx(1.20)


def test_position_size_receives_the_computed_stop_distance() -> None:
    engine = DecisionEngine(RiskPercentSizingModel(0.02), atr_multiple=2.0)
    context = MarketContext(symbol=_SYMBOL, bars=_bars())

    report = engine.decide(_signal(Direction.LONG), context, equity=10_000.0)

    assert report.recommended_stop_loss is not None
    entry_price = context.bars[-1].close
    stop_distance = entry_price - report.recommended_stop_loss
    assert report.recommended_position_size == pytest.approx(10_000.0 * 0.02 / stop_distance)


def test_rejects_invalid_phase5_construction_parameters() -> None:
    sizing = FixedVolumeSizingModel(0.1)
    with pytest.raises(ValueError, match="risk_reward_ratio_2"):
        DecisionEngine(sizing, risk_reward_ratio_2=0.0)
    with pytest.raises(ValueError, match="adx_period"):
        DecisionEngine(sizing, adx_period=1)
    with pytest.raises(ValueError, match="trend_threshold"):
        DecisionEngine(sizing, trend_threshold=0.0)
    with pytest.raises(ValueError, match="volatility_lookback"):
        DecisionEngine(sizing, volatility_lookback=1)
    with pytest.raises(ValueError, match="structure_swing_arm"):
        DecisionEngine(sizing, structure_swing_arm=0)
