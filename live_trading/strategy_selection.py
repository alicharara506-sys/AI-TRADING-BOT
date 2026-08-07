from __future__ import annotations

from collections.abc import Callable

from core.interfaces.strategy import Strategy
from strategies.pattern.fibonacci_elliott_wave import FibonacciElliottWaveStrategy
from strategies.simple.sma_crossover import SmaCrossoverStrategy

SMA_CROSSOVER = "sma_crossover"
FIBONACCI_ELLIOTT_WAVE = "fibonacci_elliott_wave"
AVAILABLE_STRATEGIES = (SMA_CROSSOVER, FIBONACCI_ELLIOTT_WAVE)


class UnknownStrategyError(ValueError):
    pass


def build_strategy_factory(
    name: str,
    *,
    fast_period: int,
    slow_period: int,
    swing_arm: int,
    lookback: int,
) -> tuple[Callable[[], Strategy], str]:
    """Maps a strategy name (as chosen via MT5_STRATEGY in the manual
    scripts) to a (factory, strategy_name) pair live_trading.runner.LiveRunner
    consumes directly. Centralized here so
    scripts/manual/run_live_strategy.py and scripts/manual/watch_signals.py
    select strategies identically rather than duplicating the mapping.
    """
    if name == SMA_CROSSOVER:
        return (
            lambda: SmaCrossoverStrategy(fast_period=fast_period, slow_period=slow_period),
            SmaCrossoverStrategy.strategy_name,
        )
    if name == FIBONACCI_ELLIOTT_WAVE:
        return (
            lambda: FibonacciElliottWaveStrategy(swing_arm=swing_arm, lookback=lookback),
            FibonacciElliottWaveStrategy.strategy_name,
        )
    raise UnknownStrategyError(
        f"Unknown MT5_STRATEGY '{name}'. Valid values: {', '.join(AVAILABLE_STRATEGIES)}"
    )


__all__ = [
    "AVAILABLE_STRATEGIES",
    "FIBONACCI_ELLIOTT_WAVE",
    "SMA_CROSSOVER",
    "UnknownStrategyError",
    "build_strategy_factory",
]
