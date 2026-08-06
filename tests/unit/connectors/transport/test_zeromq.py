from __future__ import annotations

import asyncio
import contextlib

import pytest

from connectors.transport.zeromq import ZmqPublisher, ZmqSubscriber


@pytest.mark.asyncio
async def test_publisher_subscriber_roundtrip() -> None:
    address = "tcp://127.0.0.1:28765"
    publisher = ZmqPublisher(address)
    subscriber = ZmqSubscriber(address, topics=["ticks"])
    payload = {"symbol": "EURUSD", "bid": 1.1000, "ask": 1.1002}

    async def publish_repeatedly() -> None:
        # PUB/SUB has a well-known "slow joiner" delay: the subscriber's TCP
        # connection must complete before a published message can reach it, so we
        # keep publishing until the receiver confirms it got one.
        for _ in range(40):
            await publisher.publish("ticks", payload)
            await asyncio.sleep(0.05)

    async def receive_one() -> tuple[str, dict[str, object]]:
        async for topic, received in subscriber.messages():
            return topic, received
        raise AssertionError("subscriber stream ended without a message")

    publish_task = asyncio.create_task(publish_repeatedly())
    try:
        topic, received = await asyncio.wait_for(receive_one(), timeout=5.0)
        assert topic == "ticks"
        assert received == payload
    finally:
        publish_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await publish_task
        publisher.close()
        subscriber.close()
