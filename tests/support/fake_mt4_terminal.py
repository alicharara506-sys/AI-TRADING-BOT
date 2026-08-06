from __future__ import annotations

import asyncio
import contextlib
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
)
from connectors.transport.zeromq import ZmqPublisher, ZmqReplier


class FakeMT4Terminal:
    """Stands in for the companion MQL4 Expert Advisor: a real ZmqReplier +
    ZmqPublisher on localhost, driven by a background asyncio task. MT4Connector
    tests exercise genuine ZeroMQ sockets against this, not an injected fake
    object -- a stronger check than mocking a Python SDK, since MT4 has none.
    """

    def __init__(self, command_address: str, market_data_address: str) -> None:
        self._replier = ZmqReplier(command_address)
        self._publisher = ZmqPublisher(market_data_address)
        self._task: asyncio.Task[None] | None = None

        self.connect_result: dict[str, Any] = {"ok": True}
        self.symbol_info: dict[str, Any] = {
            "digits": 5,
            "point": 0.00001,
            "contract_size": 100_000.0,
            "min_volume": 0.01,
            "max_volume": 100.0,
            "volume_step": 0.01,
            "hedging": True,
        }
        self.symbol_info_ok = True
        self.account_state: dict[str, Any] = {
            "balance": 10_000.0,
            "equity": 10_000.0,
            "margin": 0.0,
            "free_margin": 10_000.0,
            "margin_level": None,
            "currency": "USD",
        }
        self.open_positions: list[dict[str, Any]] = []
        self.trade_history: list[dict[str, Any]] = []
        self.next_order_result: dict[str, Any] = {"ok": True, "ticket": 1, "price": 1.1000}
        self.next_modify_result: dict[str, Any] = {"ok": True}
        self.next_close_result: dict[str, Any] = {"ok": True}

        self.received_requests: list[dict[str, Any]] = []

        # Fault injection: simulates the EA going briefly unresponsive --
        # the request is received (so a real terminal is observably "there")
        # but the reply is delayed, which is what actually drives
        # ZmqRequester's timeout path in a chaos test. The REP socket's own
        # recv/send alternation is still honored (the reply is delayed, not
        # skipped), so the fake terminal itself never gets stuck.
        self.stall_next_n_requests = 0
        self.stall_seconds = 1.0

    def start(self) -> None:
        self._task = asyncio.create_task(self._serve_forever())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._replier.close()
        self._publisher.close()

    async def publish_tick(self, payload: dict[str, Any]) -> None:
        await self._publisher.publish("tick", payload)

    async def publish_bar(self, payload: dict[str, Any]) -> None:
        await self._publisher.publish("bar", payload)

    async def _serve_forever(self) -> None:
        while True:
            request = await self._replier.receive()
            self.received_requests.append(request)
            if self.stall_next_n_requests > 0:
                self.stall_next_n_requests -= 1
                await asyncio.sleep(self.stall_seconds)
            await self._replier.reply(self._handle(request))

    def _handle(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == ACTION_CONNECT:
            return self.connect_result
        if action == ACTION_DISCONNECT:
            return {"ok": True}
        if action in (ACTION_SUBSCRIBE_TICKS, ACTION_SUBSCRIBE_BARS):
            return {"ok": True}
        if action == ACTION_GET_SYMBOL_INFO:
            if not self.symbol_info_ok:
                return {"ok": False, "error": "unknown symbol"}
            return {"ok": True, "symbol_info": self.symbol_info}
        if action == ACTION_GET_ACCOUNT_STATE:
            return {"ok": True, "account": self.account_state}
        if action == ACTION_GET_OPEN_POSITIONS:
            return {"ok": True, "positions": self.open_positions}
        if action == ACTION_GET_TRADE_HISTORY:
            return {"ok": True, "trades": self.trade_history}
        if action == ACTION_SUBMIT_ORDER:
            return self.next_order_result
        if action == ACTION_MODIFY_POSITION:
            return self.next_modify_result
        if action == ACTION_CLOSE_POSITION:
            return self.next_close_result
        return {"ok": False, "error": f"unknown action '{action}'"}


__all__ = ["FakeMT4Terminal"]
