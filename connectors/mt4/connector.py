from __future__ import annotations

from datetime import datetime
from typing import Any

from connectors.mt4.protocol import (
    ACTION_CLOSE_POSITION,
    ACTION_CONNECT,
    ACTION_DISCONNECT,
    ACTION_GET_ACCOUNT_STATE,
    ACTION_GET_OPEN_POSITIONS,
    ACTION_GET_SYMBOL_INFO,
    ACTION_GET_TRADE_HISTORY,
    ACTION_MODIFY_POSITION,
    ACTION_SUBMIT_ORDER,
    ACTION_SUBSCRIBE_BARS,
    ACTION_SUBSCRIBE_TICKS,
    TOPIC_BAR,
    TOPIC_TICK,
)
from connectors.mt_common.symbols import SymbolMapper
from connectors.transport.zeromq import ZmqRequester, ZmqSubscriber
from core.event_bus.bus import EventBus
from core.interfaces.events import BarClosed, ConnectionStateChanged, TickReceived
from core.interfaces.types import (
    AccountMode,
    AccountState,
    Bar,
    ConnectionState,
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Symbol,
    SymbolInfo,
    Tick,
    Timeframe,
    Trade,
)


class MT4Connector:
    """Connector Protocol implementation for MetaTrader 4. MT4 has no official
    Python API, so this is a thin client over the wire: order commands go out
    via ZmqRequester (REQ/REP) to a companion MQL4 Expert Advisor, and
    ticks/bars stream in via ZmqSubscriber (PUB/SUB) from that same EA. The EA
    itself contains no decision logic -- it only executes exactly the commands
    it's sent and forwards exactly the market/account events it observes, per
    the architecture's "thin forwarder only" requirement.
    """

    def __init__(
        self,
        requester: ZmqRequester,
        subscriber: ZmqSubscriber,
        event_bus: EventBus,
        *,
        symbol_mapper: SymbolMapper | None = None,
    ) -> None:
        self._requester = requester
        self._subscriber = subscriber
        self._event_bus = event_bus
        self._symbol_mapper = symbol_mapper or SymbolMapper()
        self._connected = False

    # -- lifecycle -----------------------------------------------------------

    async def connect(self) -> None:
        response = await self._requester.request({"action": ACTION_CONNECT})
        if not response.get("ok", False):
            raise ConnectionError(
                f"MT4 EA connect failed: {response.get('error', 'unknown error')}"
            )
        self._connected = True
        await self._event_bus.publish(ConnectionStateChanged(state=ConnectionState.CONNECTED))

    async def disconnect(self) -> None:
        await self._requester.request({"action": ACTION_DISCONNECT})
        self._connected = False
        await self._event_bus.publish(ConnectionStateChanged(state=ConnectionState.DISCONNECTED))

    def is_connected(self) -> bool:
        return self._connected

    async def listen(self) -> None:
        """Consumes the EA's tick/bar stream and republishes it onto the kernel
        Event Bus, translating the wire protocol into canonical Tick/Bar
        events. Runs until cancelled -- callers drive this as a background
        task alongside connect().
        """
        async for topic, payload in self._subscriber.messages():
            if topic == TOPIC_TICK:
                await self._event_bus.publish(TickReceived(tick=self._parse_tick(payload)))
            elif topic == TOPIC_BAR:
                await self._event_bus.publish(BarClosed(bar=self._parse_bar(payload)))

    # -- subscriptions ---------------------------------------------------------

    async def subscribe_ticks(self, symbol: Symbol) -> None:
        await self._requester.request(
            {"action": ACTION_SUBSCRIBE_TICKS, "symbol": self._symbol_mapper.to_broker(symbol)}
        )

    async def subscribe_bars(self, symbol: Symbol, timeframe: Timeframe) -> None:
        await self._requester.request(
            {
                "action": ACTION_SUBSCRIBE_BARS,
                "symbol": self._symbol_mapper.to_broker(symbol),
                "timeframe": timeframe.value,
            }
        )

    # -- queries -----------------------------------------------------------

    async def get_symbol_info(self, symbol: Symbol) -> SymbolInfo:
        response = await self._requester.request(
            {"action": ACTION_GET_SYMBOL_INFO, "symbol": self._symbol_mapper.to_broker(symbol)}
        )
        if not response.get("ok", False):
            raise LookupError(f"Unknown symbol '{symbol.canonical}': {response.get('error')}")
        data = response["symbol_info"]
        account_mode = AccountMode.HEDGING if data.get("hedging", True) else AccountMode.NETTING
        return SymbolInfo(
            symbol=symbol,
            digits=data["digits"],
            point=data["point"],
            contract_size=data["contract_size"],
            min_volume=data["min_volume"],
            max_volume=data["max_volume"],
            volume_step=data["volume_step"],
            account_mode=account_mode,
        )

    async def get_trade_history(self, from_ts: datetime, to_ts: datetime) -> list[Trade]:
        response = await self._requester.request(
            {
                "action": ACTION_GET_TRADE_HISTORY,
                "from_ts": from_ts.isoformat(),
                "to_ts": to_ts.isoformat(),
            }
        )
        return [self._parse_trade(item) for item in response.get("trades", [])]

    async def get_open_positions(self) -> list[Position]:
        response = await self._requester.request({"action": ACTION_GET_OPEN_POSITIONS})
        return [self._parse_position(item) for item in response.get("positions", [])]

    async def get_account_state(self) -> AccountState:
        response = await self._requester.request({"action": ACTION_GET_ACCOUNT_STATE})
        data = response["account"]
        return AccountState(
            balance=data["balance"],
            equity=data["equity"],
            margin=data["margin"],
            free_margin=data["free_margin"],
            margin_level=data.get("margin_level") or None,
            currency=data["currency"],
        )

    # -- orders -----------------------------------------------------------

    async def submit_order(self, request: OrderRequest) -> OrderAck:
        if request.order_type is not OrderType.MARKET:
            raise NotImplementedError(
                f"MT4Connector currently only submits market orders, got {request.order_type}"
            )
        payload: dict[str, Any] = {
            "action": ACTION_SUBMIT_ORDER,
            "correlation_id": request.correlation_id,
            "symbol": self._symbol_mapper.to_broker(request.symbol),
            "side": request.side.value,
            "volume": request.volume,
        }
        if request.stop_loss is not None:
            payload["stop_loss"] = request.stop_loss
        if request.take_profit is not None:
            payload["take_profit"] = request.take_profit

        response = await self._requester.request(payload)
        if not response.get("ok", False):
            return OrderAck(
                correlation_id=request.correlation_id,
                broker_order_id="",
                status=OrderStatus.REJECTED,
                reason=response.get("error", "order rejected"),
            )
        return OrderAck(
            correlation_id=request.correlation_id,
            broker_order_id=str(response["ticket"]),
            status=OrderStatus.FILLED,
            fill_price=response["price"],
        )

    async def modify_position(
        self,
        position_id: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None:
        response = await self._requester.request(
            {
                "action": ACTION_MODIFY_POSITION,
                "ticket": position_id,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }
        )
        if not response.get("ok", False):
            raise RuntimeError(
                f"Failed to modify position '{position_id}': {response.get('error')}"
            )

    async def close_position(self, position_id: str, *, volume: float | None = None) -> None:
        response = await self._requester.request(
            {"action": ACTION_CLOSE_POSITION, "ticket": position_id, "volume": volume}
        )
        if not response.get("ok", False):
            raise RuntimeError(f"Failed to close position '{position_id}': {response.get('error')}")

    # -- wire <-> domain translation -----------------------------------------

    def _parse_tick(self, payload: dict[str, Any]) -> Tick:
        return Tick(
            symbol=self._symbol_mapper.from_broker(payload["symbol"]),
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            bid=payload["bid"],
            ask=payload["ask"],
            volume=payload.get("volume", 0.0),
        )

    def _parse_bar(self, payload: dict[str, Any]) -> Bar:
        return Bar(
            symbol=self._symbol_mapper.from_broker(payload["symbol"]),
            timeframe=Timeframe(payload["timeframe"]),
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            open=payload["open"],
            high=payload["high"],
            low=payload["low"],
            close=payload["close"],
            volume=payload.get("volume", 0.0),
        )

    def _parse_position(self, item: dict[str, Any]) -> Position:
        return Position(
            position_id=str(item["ticket"]),
            symbol=self._symbol_mapper.from_broker(item["symbol"]),
            side=OrderSide.BUY if item["side"] == "buy" else OrderSide.SELL,
            volume=item["volume"],
            open_price=item["open_price"],
            stop_loss=item.get("stop_loss") or None,
            take_profit=item.get("take_profit") or None,
        )

    def _parse_trade(self, item: dict[str, Any]) -> Trade:
        return Trade(
            trade_id=str(item["trade_id"]),
            symbol=self._symbol_mapper.from_broker(item["symbol"]),
            side=OrderSide.BUY if item["side"] == "buy" else OrderSide.SELL,
            volume=item["volume"],
            open_price=item["open_price"],
            close_price=item["close_price"],
            open_time=datetime.fromisoformat(item["open_time"]),
            close_time=datetime.fromisoformat(item["close_time"]),
            profit=item["profit"],
        )


__all__ = ["MT4Connector"]
