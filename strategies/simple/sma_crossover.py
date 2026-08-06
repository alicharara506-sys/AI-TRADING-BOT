from __future__ import annotations

from core.indicators.trend import SimpleMovingAverage
from core.interfaces.types import Bar, Direction, Evidence, TradeSignal


class SmaCrossoverStrategy:
    """Simple-mode strategy (init()/on_bar() authoring): fast/slow SMA crossover.
    Emits a TradeSignal exactly on the bar a crossover occurs, None otherwise
    (hold). A strategy this simple is its own single Evidence source, at full
    confidence -- there is no separate Signal Fusion step to hand it off to yet,
    so it produces a directly-actionable signal rather than raw Evidence.
    """

    strategy_name = "sma_crossover"

    def __init__(self, *, fast_period: int = 5, slow_period: int = 20) -> None:
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._fast = SimpleMovingAverage(period=fast_period)
        self._slow = SimpleMovingAverage(period=slow_period)
        self._was_fast_above_slow: bool | None = None

    def on_bar(self, bar: Bar) -> TradeSignal | None:
        fast_value = self._fast.update(bar)
        slow_value = self._slow.update(bar)
        if fast_value is None or slow_value is None:
            return None
        if fast_value == slow_value:
            # Exactly flat (common with repeated/round prices): no directional
            # state change to report, and not a crossover in either direction --
            # a naive strict '>' comparison would otherwise flip state spuriously
            # the instant the two averages land on the same float.
            return None

        is_fast_above_slow = fast_value > slow_value
        previous = self._was_fast_above_slow
        self._was_fast_above_slow = is_fast_above_slow

        if previous is None or is_fast_above_slow == previous:
            return None

        direction = Direction.LONG if is_fast_above_slow else Direction.SHORT
        evidence = Evidence(
            source_module=self.strategy_name,
            direction=direction,
            confidence=1.0,
            rationale={
                "event": "sma_crossover",
                "fast_period": self._fast_period,
                "slow_period": self._slow_period,
            },
            supporting_data={"fast": fast_value, "slow": slow_value},
        )
        return TradeSignal(
            symbol=bar.symbol,
            direction=direction,
            combined_confidence=1.0,
            threshold=0.0,
            evidence=(evidence,),
        )


__all__ = ["SmaCrossoverStrategy"]
