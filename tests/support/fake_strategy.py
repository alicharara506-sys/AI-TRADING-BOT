from __future__ import annotations

from core.interfaces.types import Bar, Direction, Evidence, TradeSignal


class AlwaysFlipStrategy:
    """Test double: emits a full-confidence signal on every single bar,
    alternating LONG/SHORT starting with LONG. Used where a test needs
    precise control over exactly how many round-trip trades a backtest
    produces, without depending on SmaCrossoverStrategy's SMA math to line
    up a specific number of crossovers.
    """

    strategy_name = "always_flip"

    def __init__(self) -> None:
        self._next_direction = Direction.LONG

    def on_bar(self, bar: Bar) -> TradeSignal | None:
        direction = self._next_direction
        self._next_direction = (
            Direction.SHORT if direction is Direction.LONG else Direction.LONG
        )
        evidence = Evidence(
            source_module=self.strategy_name, direction=direction, confidence=1.0
        )
        return TradeSignal(
            symbol=bar.symbol,
            direction=direction,
            combined_confidence=1.0,
            threshold=0.0,
            evidence=(evidence,),
        )


__all__ = ["AlwaysFlipStrategy"]
