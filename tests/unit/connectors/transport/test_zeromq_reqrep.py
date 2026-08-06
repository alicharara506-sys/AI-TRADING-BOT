from __future__ import annotations

import asyncio
import contextlib

import pytest

from connectors.transport.zeromq import ZmqReplier, ZmqRequester


@pytest.mark.asyncio
async def test_requester_replier_roundtrip() -> None:
    address = "tcp://127.0.0.1:28766"
    replier = ZmqReplier(address)
    requester = ZmqRequester(address, timeout_seconds=5.0)

    async def serve_one() -> None:
        request = await replier.receive()
        assert request == {"action": "ping"}
        await replier.reply({"ok": True, "action": request["action"]})

    server_task = asyncio.create_task(serve_one())
    try:
        response = await requester.request({"action": "ping"})
        assert response == {"ok": True, "action": "ping"}
        await server_task
    finally:
        requester.close()
        replier.close()
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task


@pytest.mark.asyncio
async def test_multiple_sequential_requests_stay_in_lockstep() -> None:
    address = "tcp://127.0.0.1:28767"
    replier = ZmqReplier(address)
    requester = ZmqRequester(address, timeout_seconds=5.0)

    async def serve(n: int) -> None:
        for _ in range(n):
            request = await replier.receive()
            await replier.reply({"echo": request["value"]})

    server_task = asyncio.create_task(serve(3))
    try:
        for value in (1, 2, 3):
            response = await requester.request({"value": value})
            assert response == {"echo": value}
        await server_task
    finally:
        requester.close()
        replier.close()


@pytest.mark.asyncio
async def test_request_times_out_when_nothing_replies() -> None:
    address = "tcp://127.0.0.1:28768"
    replier = ZmqReplier(address)  # bound, but nothing ever calls receive()/reply()
    requester = ZmqRequester(address, timeout_seconds=0.2)

    try:
        with pytest.raises(TimeoutError):
            await requester.request({"action": "ping"})
    finally:
        requester.close()
        replier.close()
