from __future__ import annotations

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


__all__ = ["ZmqPublisher", "ZmqSubscriber"]
