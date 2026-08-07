from __future__ import annotations

from collections.abc import Callable

from core.event_bus.bus import EventBus
from core.interfaces.events import BarClosed
from core.interfaces.strategy import Strategy
from core.interfaces.types import Bar, Symbol, TradeSignal


class SignalWatcher:
    """Watches BarClosed events for one symbol and reports every TradeSignal
    a strategy emits -- never submits an order itself.

    For a broker/account where the venue's own server disallows automated
    order submission (e.g. MT5 retcode 10026, "AutoTrading disabled by
    server" -- a server-side permission this platform cannot grant or route
    around), this is the honest fallback: the same strategy driven by the
    same real market data as LiveRunner, surfaced as an alert for a human to
    act on manually in the terminal, rather than silently doing nothing.
    """

    def __init__(
        self,
        symbol: Symbol,
        strategy: Strategy,
        event_bus: EventBus,
        *,
        on_signal: Callable[[TradeSignal, Bar], None],
    ) -> None:
        self._symbol = symbol
        self._strategy = strategy
        self._on_signal = on_signal
        event_bus.subscribe(BarClosed, self._on_bar)

    async def _on_bar(self, event: BarClosed) -> None:
        if event.bar.symbol.canonical != self._symbol.canonical:
            return
        signal = self._strategy.on_bar(event.bar)
        if signal is not None:
            self._on_signal(signal, event.bar)


__all__ = ["SignalWatcher"]
