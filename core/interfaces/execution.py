from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.interfaces.types import OrderAck, OrderRequest


@runtime_checkable
class ExecutionEngine(Protocol):
    async def submit_order(self, request: OrderRequest) -> OrderAck: ...

    async def cancel_order(self, correlation_id: str) -> None: ...
