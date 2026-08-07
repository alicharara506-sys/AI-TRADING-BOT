from __future__ import annotations

from collections.abc import Callable

from core.interfaces.strategy import Strategy
from core.interfaces.types import Timeframe
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from strategies.composite.module_roster import build_default_module_roster
from strategies.composite.signal_fusion_strategy import SignalFusionStrategy
from strategies.pattern.fibonacci_elliott_wave import FibonacciElliottWaveStrategy
from strategies.simple.sma_crossover import SmaCrossoverStrategy

SMA_CROSSOVER = "sma_crossover"
FIBONACCI_ELLIOTT_WAVE = "fibonacci_elliott_wave"
SIGNAL_FUSION = "signal_fusion"
AVAILABLE_STRATEGIES = (SMA_CROSSOVER, FIBONACCI_ELLIOTT_WAVE, SIGNAL_FUSION)


class UnknownStrategyError(ValueError):
    pass


def build_strategy_factory(
    name: str,
    *,
    fast_period: int,
    slow_period: int,
    swing_arm: int,
    lookback: int,
    signal_fusion_threshold: float = 0.6,
    higher_timeframe: Timeframe | None = Timeframe.H4,
) -> tuple[Callable[[], Strategy], str]:
    """Maps a strategy name (as chosen via MT5_STRATEGY in the manual
    scripts) to a (factory, strategy_name) pair live_trading.runner.LiveRunner
    consumes directly. Centralized here so
    scripts/manual/run_live_strategy.py, scripts/manual/watch_signals.py, and
    scripts/manual/run_dashboard_feed.py select strategies identically rather
    than duplicating the mapping.
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
    if name == SIGNAL_FUSION:

        def _build_signal_fusion_strategy() -> SignalFusionStrategy:
            engine = SignalEngine(SignalFusion(threshold=signal_fusion_threshold))
            for module in build_default_module_roster(
                swing_arm=swing_arm, higher_timeframe=higher_timeframe
            ):
                engine.register_module(module)
            return SignalFusionStrategy(
                engine, strategy_name=SIGNAL_FUSION, lookback=lookback
            )

        return _build_signal_fusion_strategy, SIGNAL_FUSION
    raise UnknownStrategyError(
        f"Unknown MT5_STRATEGY '{name}'. Valid values: {', '.join(AVAILABLE_STRATEGIES)}"
    )


__all__ = [
    "AVAILABLE_STRATEGIES",
    "FIBONACCI_ELLIOTT_WAVE",
    "SIGNAL_FUSION",
    "SMA_CROSSOVER",
    "UnknownStrategyError",
    "build_strategy_factory",
]
