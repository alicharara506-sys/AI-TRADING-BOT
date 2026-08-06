from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import zmq
import zmq.asyncio


class ZmqPublisher:
    """PUB side of the tick/bar/account streaming channel. One process (the MT5
    bridge) publishes; any number of subscribers (kernel processes) can attach."""

    def __init__(self, bind_address: str, *, context: zmq.asyncio.Context | None = None) -> None:
        self._context = context or zmq.asyncio.Context.instance()
        self._socket = self._context.socket(zmq.PUB)
        self._socket.bind(bind_address)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        message = json.dumps(payload).encode("utf-8")
        await self._socket.send_multipart([topic.encode("utf-8"), message])

    def close(self) -> None:
        self._socket.close(linger=0)


class ZmqSubscriber:
    """SUB side: connects to a publisher and yields (topic, payload) for every
    topic it was constructed with."""

    def __init__(
        self,
        connect_address: str,
        topics: list[str],
        *,
        context: zmq.asyncio.Context | None = None,
    ) -> None:
        self._context = context or zmq.asyncio.Context.instance()
        self._socket = self._context.socket(zmq.SUB)
        self._socket.connect(connect_address)
        for topic in topics:
            self._socket.setsockopt(zmq.SUBSCRIBE, topic.encode("utf-8"))

    async def messages(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        while True:
            topic_bytes, payload_bytes = await self._socket.recv_multipart()
            yield topic_bytes.decode("utf-8"), json.loads(payload_bytes.decode("utf-8"))

    def close(self) -> None:
        self._socket.close(linger=0)


class ZmqRequester:
    """REQ side of the command/ack channel: submit_order, modify, close, and
    query calls block for a reply. ZeroMQ's REQ socket enforces strict
    lock-step (send, then recv, then send again) -- exactly the request/reply
    discipline a single in-flight command needs.
    """

    def __init__(
        self,
        connect_address: str,
        *,
        context: zmq.asyncio.Context | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._context = context or zmq.asyncio.Context.instance()
        self._socket = self._context.socket(zmq.REQ)
        self._socket.connect(connect_address)
        self._timeout_seconds = timeout_seconds

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = json.dumps(payload).encode("utf-8")
        await self._socket.send(message)
        try:
            response = await asyncio.wait_for(self._socket.recv(), timeout=self._timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(
                f"No reply within {self._timeout_seconds}s for action "
                f"'{payload.get('action', '?')}'"
            ) from exc
        result: dict[str, Any] = json.loads(response.decode("utf-8"))
        return result

    def close(self) -> None:
        self._socket.close(linger=0)


class ZmqReplier:
    """REP side: the command/ack channel's server. Must reply to each request
    before receiving the next -- ZeroMQ enforces this pairing at the socket
    level, so a bridge (e.g. the MT4 EA) built on this can never get out of
    sync with its client.
    """

    def __init__(self, bind_address: str, *, context: zmq.asyncio.Context | None = None) -> None:
        self._context = context or zmq.asyncio.Context.instance()
        self._socket = self._context.socket(zmq.REP)
        self._socket.bind(bind_address)

    async def receive(self) -> dict[str, Any]:
        message = await self._socket.recv()
        result: dict[str, Any] = json.loads(message.decode("utf-8"))
        return result

    async def reply(self, payload: dict[str, Any]) -> None:
        await self._socket.send(json.dumps(payload).encode("utf-8"))

    def close(self) -> None:
        self._socket.close(linger=0)


__all__ = ["ZmqPublisher", "ZmqReplier", "ZmqRequester", "ZmqSubscriber"]
