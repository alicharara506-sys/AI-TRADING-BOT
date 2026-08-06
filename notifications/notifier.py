from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from typing import Protocol, runtime_checkable

from core.logging.setup import get_logger


@runtime_checkable
class Notifier(Protocol):
    async def send(self, subject: str, body: str) -> None: ...


class LoggingNotifier:
    """The simplest real notifier: writes to the platform's structured
    logger. A legitimate notification channel in its own right (operators
    watching logs or a log aggregator), not a stand-in for a "real" one.
    """

    def __init__(self, *, logger_name: str = "notifications") -> None:
        self._logger = get_logger(logger_name)

    async def send(self, subject: str, body: str) -> None:
        self._logger.info("%s: %s", subject, body)


class WebhookNotifier:
    """Posts a JSON payload to a configured webhook URL (Slack/Telegram/
    generic webhook adapters all reduce to this shape). Uses the stdlib's
    synchronous urllib, off-loaded to a worker thread via asyncio.to_thread
    so it doesn't block the event loop -- no new HTTP client dependency
    needed for a single POST call.
    """

    def __init__(self, url: str, *, timeout_seconds: float = 5.0) -> None:
        if not url:
            raise ValueError("url must not be empty")
        scheme = urllib.parse.urlsplit(url).scheme
        if scheme not in ("http", "https"):
            raise ValueError(f"url must be http(s), got scheme '{scheme}'")
        self._url = url
        self._timeout_seconds = timeout_seconds

    async def send(self, subject: str, body: str) -> None:
        payload = json.dumps({"subject": subject, "body": body}).encode("utf-8")
        await asyncio.to_thread(self._post, payload)

    def _post(self, payload: bytes) -> None:
        request = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            response.read()


__all__ = ["LoggingNotifier", "Notifier", "WebhookNotifier"]
