from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# Documented constants from the official `MetaTrader5` package. Mirrored here
# rather than imported: that package is a Windows-only local IPC bridge to a
# running MT5 terminal and cannot be installed in this environment. Production
# deployments inject the real module (or any object satisfying MT5Api) at
# construction time; tests inject a fake.
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1

TRADE_ACTION_DEAL = 1
TRADE_ACTION_SLTP = 2
TRADE_ACTION_REMOVE = 3

TRADE_RETCODE_DONE = 10009

ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2

DEAL_ENTRY_IN = 0
DEAL_ENTRY_OUT = 1

TIMEFRAME_M1 = 1
TIMEFRAME_M5 = 5
TIMEFRAME_M15 = 15
TIMEFRAME_M30 = 30
TIMEFRAME_H1 = 16385
TIMEFRAME_H4 = 16388
TIMEFRAME_D1 = 16408
TIMEFRAME_W1 = 32769
TIMEFRAME_MN1 = 49153

TIMEFRAME_MAP: dict[str, int] = {
    "M1": TIMEFRAME_M1,
    "M5": TIMEFRAME_M5,
    "M15": TIMEFRAME_M15,
    "M30": TIMEFRAME_M30,
    "H1": TIMEFRAME_H1,
    "H4": TIMEFRAME_H4,
    "D1": TIMEFRAME_D1,
    "W1": TIMEFRAME_W1,
    "MN1": TIMEFRAME_MN1,
}


@runtime_checkable
class MT5Api(Protocol):
    """The subset of the official `MetaTrader5` package's module-level functions
    this connector depends on."""

    def initialize(self, **kwargs: Any) -> bool: ...

    def login(self, login: int, password: str, server: str) -> bool: ...

    def shutdown(self) -> None: ...

    def last_error(self) -> tuple[int, str]: ...

    def account_info(self) -> Any: ...

    def symbol_info(self, symbol: str) -> Any: ...

    def symbol_info_tick(self, symbol: str) -> Any: ...

    def copy_rates_from_pos(
        self, symbol: str, timeframe: int, start_pos: int, count: int
    ) -> Any: ...

    def order_send(self, request: dict[str, Any]) -> Any: ...

    def positions_get(self, *, symbol: str | None = None) -> Any: ...

    def history_deals_get(self, date_from: Any, date_to: Any) -> Any: ...


__all__ = [
    "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING",
    "ACCOUNT_MARGIN_MODE_RETAIL_NETTING",
    "DEAL_ENTRY_IN",
    "DEAL_ENTRY_OUT",
    "ORDER_TYPE_BUY",
    "ORDER_TYPE_SELL",
    "TIMEFRAME_MAP",
    "TRADE_ACTION_DEAL",
    "TRADE_ACTION_REMOVE",
    "TRADE_ACTION_SLTP",
    "TRADE_RETCODE_DONE",
    "MT5Api",
]
