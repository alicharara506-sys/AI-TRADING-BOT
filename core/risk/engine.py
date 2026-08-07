from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

from core.event_bus.bus import EventBus
from core.interfaces.clock import Clock
from core.interfaces.events import AccountStateChanged
from core.interfaces.types import OrderRequest, TradeSignal
from core.kernel.clock import LiveClock
from core.portfolio.engine import PortfolioEngine


class RiskEngine:
    """Minimum viable institutional safety floor: a kill switch, a max-open-
    positions limit, and a daily-loss limit. Veto is expressed by returning None,
    never by raising, so callers (RiskGatedExecutionEngine) can treat "no" as an
    ordinary outcome rather than an exceptional one.

    The five new filters below (max drawdown, correlation, spread, exposure,
    min risk/reward) are each independently optional -- every constructor
    parameter defaults to None (disabled), so an existing RiskEngine(...)
    call site keeps its exact original behavior. Correlation/spread/exposure/
    min-RR are pure, stateless checks: the caller supplies whatever data the
    check needs (a correlation matrix, a spread, an exposure figure, a
    risk/reward ratio) rather than RiskEngine fetching or computing it
    itself -- the same separation of concerns ValidationPipeline already
    uses (it receives trade_returns, it doesn't run its own backtest).
    """

    def __init__(
        self,
        portfolio: PortfolioEngine,
        event_bus: EventBus,
        *,
        max_open_positions: int,
        daily_loss_limit: float,
        clock: Clock | None = None,
        max_drawdown_percent: float | None = None,
        max_correlation: float | None = None,
        max_spread: float | None = None,
        max_exposure: float | None = None,
        min_risk_reward_ratio: float | None = None,
    ) -> None:
        if max_open_positions < 1:
            raise ValueError("max_open_positions must be >= 1")
        if daily_loss_limit <= 0:
            raise ValueError("daily_loss_limit must be > 0")
        if max_drawdown_percent is not None and not 0.0 < max_drawdown_percent < 100.0:
            raise ValueError("max_drawdown_percent must be in (0.0, 100.0)")
        if max_correlation is not None and not 0.0 < max_correlation <= 1.0:
            raise ValueError("max_correlation must be in (0.0, 1.0]")
        if max_spread is not None and max_spread <= 0:
            raise ValueError("max_spread must be > 0")
        if max_exposure is not None and max_exposure <= 0:
            raise ValueError("max_exposure must be > 0")
        if min_risk_reward_ratio is not None and min_risk_reward_ratio <= 0:
            raise ValueError("min_risk_reward_ratio must be > 0")
        self._portfolio = portfolio
        self._max_open_positions = max_open_positions
        self._daily_loss_limit = daily_loss_limit
        self._clock = clock or LiveClock()
        self._max_drawdown_percent = max_drawdown_percent
        self._max_correlation = max_correlation
        self._max_spread = max_spread
        self._max_exposure = max_exposure
        self._min_risk_reward_ratio = min_risk_reward_ratio
        self._kill_switch_engaged = False
        self._kill_switch_reason: str | None = None
        self._current_day: date | None = None
        self._day_start_equity: float | None = None
        self._current_equity: float | None = None
        self._peak_equity: float | None = None
        event_bus.subscribe(AccountStateChanged, self._on_account_state_changed)

    def engage_kill_switch(self, reason: str) -> None:
        self._kill_switch_engaged = True
        self._kill_switch_reason = reason

    def reset_kill_switch(self) -> None:
        self._kill_switch_engaged = False
        self._kill_switch_reason = None

    def is_kill_switch_engaged(self) -> bool:
        return self._kill_switch_engaged

    @property
    def kill_switch_reason(self) -> str | None:
        return self._kill_switch_reason

    async def _on_account_state_changed(self, event: AccountStateChanged) -> None:
        today = self._clock.now().date()
        if self._current_day != today:
            self._current_day = today
            self._day_start_equity = event.account_state.equity
        self._current_equity = event.account_state.equity
        self._check_daily_loss_limit()
        self._check_max_drawdown()

    def _check_daily_loss_limit(self) -> None:
        if self._day_start_equity is None or self._current_equity is None:
            return
        loss = self._day_start_equity - self._current_equity
        if loss >= self._daily_loss_limit and not self._kill_switch_engaged:
            self.engage_kill_switch(
                f"Daily loss limit breached: {loss:.2f} >= {self._daily_loss_limit:.2f}"
            )

    def _check_max_drawdown(self) -> None:
        if self._max_drawdown_percent is None or self._current_equity is None:
            return
        if self._peak_equity is None or self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity
            return
        drawdown_percent = (self._peak_equity - self._current_equity) / self._peak_equity * 100.0
        if drawdown_percent >= self._max_drawdown_percent and not self._kill_switch_engaged:
            self.engage_kill_switch(
                f"Max drawdown breached: {drawdown_percent:.2f}% "
                f">= {self._max_drawdown_percent:.2f}% (peak equity {self._peak_equity:.2f})"
            )

    def _positions_at_capacity(self) -> bool:
        return self._portfolio.open_position_count() >= self._max_open_positions

    def evaluate_signal(self, signal: TradeSignal) -> TradeSignal | None:
        if self._kill_switch_engaged or self._positions_at_capacity():
            return None
        return signal

    def evaluate_order(self, request: OrderRequest) -> OrderRequest | None:
        if self._kill_switch_engaged or self._positions_at_capacity():
            return None
        return request

    def evaluate_correlation(
        self,
        symbol: str,
        *,
        correlation_matrix: Mapping[str, Mapping[str, float]],
        open_symbols: Iterable[str],
    ) -> bool:
        """True (pass) unless `max_correlation` is configured and `symbol` is
        at or above it with some other currently-open symbol -- reusing
        quant.statistics.correlation.compute_correlation_matrix's output
        (the caller computes it; RiskEngine only judges it) so a new
        position doesn't silently stack correlated risk on an existing one.
        """
        if self._max_correlation is None:
            return True
        row = correlation_matrix.get(symbol)
        if row is None:
            return True
        for open_symbol in open_symbols:
            if open_symbol == symbol:
                continue
            correlation = row.get(open_symbol)
            if correlation is not None and abs(correlation) >= self._max_correlation:
                return False
        return True

    def evaluate_spread(self, spread: float) -> bool:
        """True (pass) unless `max_spread` is configured and `spread`
        exceeds it -- a wide quoted spread is both a direct cost and,
        especially in retail FX/CFD venues, a proxy for the slippage a
        market order is likely to suffer right now.
        """
        if self._max_spread is None:
            return True
        return spread <= self._max_spread

    def evaluate_exposure(self, *, current_exposure: float, additional_volume: float) -> bool:
        """True (pass) unless `max_exposure` is configured and adding
        `additional_volume` to `current_exposure` (whatever notional/volume
        unit the caller tracks exposure in) would exceed it.
        """
        if self._max_exposure is None:
            return True
        return current_exposure + additional_volume <= self._max_exposure

    def evaluate_min_risk_reward(self, risk_reward_ratio: float | None) -> bool:
        """True (pass) unless `min_risk_reward_ratio` is configured and the
        trade's own risk_reward_ratio (decision_engine.report.DecisionReport
        already computes it) falls short -- or is missing entirely, which
        fails closed rather than passing a trade with an unknown ratio.
        """
        if self._min_risk_reward_ratio is None:
            return True
        if risk_reward_ratio is None:
            return False
        return risk_reward_ratio >= self._min_risk_reward_ratio


__all__ = ["RiskEngine"]
