from __future__ import annotations

import pytest

from core.kernel.lifecycle import Kernel


class _RecordingComponent:
    def __init__(self, log: list[str], name: str) -> None:
        self._log = log
        self._name = name

    async def start(self) -> None:
        self._log.append(f"start:{self._name}")

    async def stop(self) -> None:
        self._log.append(f"stop:{self._name}")


@pytest.mark.asyncio
async def test_components_start_in_order_and_stop_in_reverse() -> None:
    log: list[str] = []
    kernel = Kernel()
    kernel.register_component(_RecordingComponent(log, "a"))
    kernel.register_component(_RecordingComponent(log, "b"))

    await kernel.start()
    await kernel.stop()

    assert log == ["start:a", "start:b", "stop:b", "stop:a"]
