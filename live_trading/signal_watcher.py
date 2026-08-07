from __future__ import annotations

from collections.abc import Callable, Sequence

from core.event_bus.bus import EventBus
from core.interfaces.events import BarClosed
from core.interfaces.strategy import Strategy
from core.interfaces.types import Bar, Symbol, TradeSignal

_DEFAULT_MAX_HISTORY = 500


class SignalWatcher:
    """Watches BarClosed events for one symbol and reports every TradeSignal
    a strategy emits -- never submits an order itself.

    For a broker/account where the venue's own server disallows automated
    order submission (e.g. MT5 retcode 10026, "AutoTrading disabled by
    server" -- a server-side permission this platform cannot grant or route
    around), this is the honest fallback: the same strategy driven by the
    same real market data as LiveRunner, surfaced as an alert for a human to
    act on manually in the terminal, rather than silently doing nothing.

    Also maintains a bounded rolling history of every bar seen (seedable
    with already-fetched historical bars at construction), passed alongside
    each signal so a caller can compute ATR-based stop-loss/take-profit via
    decision_engine.engine.DecisionEngine without needing its own separate
    bar-tracking subscriber.
    """

    def __init__(
        self,
        symbol: Symbol,
        strategy: Strategy,
        event_bus: EventBus,
        *,
        on_signal: Callable[[TradeSignal, Bar, tuple[Bar, ...]], None],
        history: Sequence[Bar] = (),
        max_history: int = _DEFAULT_MAX_HISTORY,
    ) -> None:
        self._symbol = symbol
        self._strategy = strategy
        self._on_signal = on_signal
        self._max_history = max_history
        self._history: list[Bar] = [
            bar for bar in history if bar.symbol.canonical == symbol.canonical
        ]
        self._trim_history()
        event_bus.subscribe(BarClosed, self._on_bar)

    def _trim_history(self) -> None:
        if len(self._history) > self._max_history:
            del self._history[: len(self._history) - self._max_history]

    async def _on_bar(self, event: BarClosed) -> None:
        if event.bar.symbol.canonical != self._symbol.canonical:
            return
        self._history.append(event.bar)
        self._trim_history()
        signal = self._strategy.on_bar(event.bar)
        if signal is not None:
            self._on_signal(signal, event.bar, tuple(self._history))


__all__ = ["SignalWatcher"]
