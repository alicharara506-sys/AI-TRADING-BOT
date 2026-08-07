from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from connectors.mt5.api import ACCOUNT_MARGIN_MODE_RETAIL_HEDGING, TRADE_RETCODE_DONE


@dataclass
class FakeAccount:
    balance: float = 10_000.0
    equity: float = 10_000.0
    margin: float = 0.0
    margin_free: float = 10_000.0
    margin_level: float = 0.0
    currency: str = "USD"
    margin_mode: int = ACCOUNT_MARGIN_MODE_RETAIL_HEDGING


@dataclass
class FakeSymbolInfo:
    digits: int = 5
    point: float = 0.00001
    trade_contract_size: float = 100_000.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01


@dataclass
class FakeTick:
    time: float
    bid: float
    ask: float
    volume: float = 0.0


@dataclass
class FakePosition:
    ticket: int
    symbol: str
    type: int
    volume: float
    price_open: float
    sl: float = 0.0
    tp: float = 0.0


@dataclass
class FakeOrderResult:
    retcode: int
    order: int = 0
    comment: str = ""
    price: float = 0.0


@dataclass
class FakeDeal:
    position_id: int
    symbol: str
    type: int
    volume: float
    price: float
    time: float
    profit: float
    entry: int


class FakeMT5Api:
    """Structurally satisfies MT5Api without needing the real MetaTrader5
    package. Any method can be monkey-patched per-test to raise or return a
    failure for N calls then recover -- the pattern used to simulate an API
    outage in both the poll-loop and order-path fault-tolerance tests.
    """

    def __init__(self) -> None:
        self.account = FakeAccount()
        self.symbols: dict[str, FakeSymbolInfo] = {"EURUSD": FakeSymbolInfo()}
        self.ticks: dict[str, FakeTick] = {}
        self.rates: dict[tuple[str, int], list[dict[str, Any]]] = {}
        self.positions: list[FakePosition] = []
        self.deals: list[FakeDeal] = []
        self.sent_requests: list[dict[str, Any]] = []
        self.next_order_result = FakeOrderResult(retcode=TRADE_RETCODE_DONE, order=1, price=1.1005)
        self.initialize_result = True
        self.login_result = True

    def initialize(self, **kwargs: Any) -> bool:
        return self.initialize_result

    def login(self, login: int, password: str, server: str) -> bool:
        return self.login_result

    def shutdown(self) -> None:
        return None

    def last_error(self) -> tuple[int, str]:
        return (1, "simulated failure")

    def account_info(self) -> Any:
        return self.account

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        return symbol in self.symbols

    def symbol_info(self, symbol: str) -> Any:
        return self.symbols.get(symbol)

    def symbol_info_tick(self, symbol: str) -> Any:
        return self.ticks.get(symbol)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any:
        return self.rates.get((symbol, timeframe), [])[start_pos : start_pos + count]

    def order_send(self, request: dict[str, Any]) -> Any:
        self.sent_requests.append(request)
        return self.next_order_result

    def positions_get(self, *, symbol: str | None = None) -> Any:
        if symbol is None:
            return list(self.positions)
        return [p for p in self.positions if p.symbol == symbol]

    def history_deals_get(self, date_from: Any, date_to: Any) -> Any:
        return list(self.deals)


__all__ = [
    "FakeAccount",
    "FakeDeal",
    "FakeMT5Api",
    "FakeOrderResult",
    "FakePosition",
    "FakeSymbolInfo",
    "FakeTick",
]
