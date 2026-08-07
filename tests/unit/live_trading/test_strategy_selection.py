from __future__ import annotations

import pytest

from core.interfaces.types import Timeframe
from live_trading.strategy_selection import (
    FIBONACCI_ELLIOTT_WAVE,
    SIGNAL_FUSION,
    SMA_CROSSOVER,
    UnknownStrategyError,
    build_strategy_factory,
)
from strategies.composite.signal_fusion_strategy import SignalFusionStrategy
from strategies.pattern.fibonacci_elliott_wave import FibonacciElliottWaveStrategy
from strategies.simple.sma_crossover import SmaCrossoverStrategy


def test_builds_sma_crossover_with_configured_periods() -> None:
    factory, name = build_strategy_factory(
        SMA_CROSSOVER, fast_period=3, slow_period=9, swing_arm=2, lookback=300
    )

    strategy = factory()

    assert name == "sma_crossover"
    assert isinstance(strategy, SmaCrossoverStrategy)
    assert strategy._fast_period == 3  # noqa: SLF001
    assert strategy._slow_period == 9  # noqa: SLF001


def test_builds_fibonacci_elliott_wave_with_configured_params() -> None:
    factory, name = build_strategy_factory(
        FIBONACCI_ELLIOTT_WAVE, fast_period=5, slow_period=20, swing_arm=3, lookback=250
    )

    strategy = factory()

    assert name == "fibonacci_elliott_wave"
    assert isinstance(strategy, FibonacciElliottWaveStrategy)
    assert strategy._swing_arm == 3  # noqa: SLF001
    assert strategy._lookback == 250  # noqa: SLF001


def test_builds_signal_fusion_with_the_default_module_roster() -> None:
    factory, name = build_strategy_factory(
        SIGNAL_FUSION, fast_period=5, slow_period=20, swing_arm=2, lookback=300
    )

    strategy = factory()

    assert name == "signal_fusion"
    assert isinstance(strategy, SignalFusionStrategy)
    assert strategy.strategy_name == "signal_fusion"


def test_signal_fusion_respects_configured_threshold_and_higher_timeframe() -> None:
    factory, _name = build_strategy_factory(
        SIGNAL_FUSION,
        fast_period=5,
        slow_period=20,
        swing_arm=2,
        lookback=300,
        signal_fusion_threshold=0.7,
        higher_timeframe=Timeframe.D1,
    )

    strategy = factory()

    assert strategy._engine._fusion._threshold == pytest.approx(0.7)  # noqa: SLF001


def test_each_call_returns_a_fresh_strategy_instance() -> None:
    factory, _name = build_strategy_factory(
        SMA_CROSSOVER, fast_period=5, slow_period=20, swing_arm=2, lookback=300
    )

    assert factory() is not factory()


def test_unknown_strategy_name_raises() -> None:
    with pytest.raises(UnknownStrategyError):
        build_strategy_factory(
            "not_a_real_strategy", fast_period=5, slow_period=20, swing_arm=2, lookback=300
        )
