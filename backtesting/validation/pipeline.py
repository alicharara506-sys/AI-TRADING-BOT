from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from backtesting.validation.look_ahead import LookAheadBiasCheck
from backtesting.validation.monte_carlo import MonteCarloCheck
from backtesting.validation.walk_forward import WalkForwardCheck
from core.interfaces.validation import ValidationReport


class ValidationPipeline:
    """Runs every configured check and produces one ValidationReport. A strategy
    passes only when every check passes -- there is no partial credit for the
    gate that decides whether a strategy may ever reach live execution.
    """

    def __init__(
        self,
        *,
        walk_forward: WalkForwardCheck,
        monte_carlo: MonteCarloCheck,
        look_ahead: LookAheadBiasCheck,
    ) -> None:
        self._walk_forward = walk_forward
        self._monte_carlo = monte_carlo
        self._look_ahead = look_ahead

    def run(
        self,
        *,
        strategy_name: str,
        trade_returns: Sequence[float],
        bar_timestamps: Sequence[datetime],
    ) -> ValidationReport:
        checks = (
            self._walk_forward.run(trade_returns),
            self._monte_carlo.run(trade_returns),
            self._look_ahead.run(bar_timestamps),
        )
        return ValidationReport(strategy_name=strategy_name, checks=checks)


__all__ = ["ValidationPipeline"]
