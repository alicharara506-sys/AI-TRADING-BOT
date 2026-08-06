from __future__ import annotations

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
    """

    def __init__(
        self,
        portfolio: PortfolioEngine,
        event_bus: EventBus,
        *,
        max_open_positions: int,
        daily_loss_limit: float,
        clock: Clock | None = None,
    ) -> None:
        if max_open_positions < 1:
            raise ValueError("max_open_positions must be >= 1")
        if daily_loss_limit <= 0:
            raise ValueError("daily_loss_limit must be > 0")
        self._portfolio = portfolio
        self._max_open_positions = max_open_positions
        self._daily_loss_limit = daily_loss_limit
        self._clock = clock or LiveClock()
        self._kill_switch_engaged = False
        self._kill_switch_reason: str | None = None
        self._current_day: date | None = None
        self._day_start_equity: float | None = None
        self._current_equity: float | None = None
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

    def _check_daily_loss_limit(self) -> None:
        if self._day_start_equity is None or self._current_equity is None:
            return
        loss = self._day_start_equity - self._current_equity
        if loss >= self._daily_loss_limit and not self._kill_switch_engaged:
            self.engage_kill_switch(
                f"Daily loss limit breached: {loss:.2f} >= {self._daily_loss_limit:.2f}"
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


__all__ = ["RiskEngine"]
