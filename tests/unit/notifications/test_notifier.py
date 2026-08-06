from __future__ import annotations

import urllib.error

import pytest

from notifications.notifier import LoggingNotifier, WebhookNotifier
from tests.support.local_http_server import recording_http_server


async def test_logging_notifier_sends_without_raising() -> None:
    notifier = LoggingNotifier()

    await notifier.send("Test Subject", "Test Body")


def test_webhook_notifier_rejects_empty_url() -> None:
    with pytest.raises(ValueError, match="url"):
        WebhookNotifier("")


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"]
)
def test_webhook_notifier_rejects_non_http_schemes(url: str) -> None:
    with pytest.raises(ValueError, match="http"):
        WebhookNotifier(url)


async def test_webhook_notifier_posts_json_payload_to_a_real_server() -> None:
    with recording_http_server(port=18581) as server:
        notifier = WebhookNotifier(f"http://127.0.0.1:{server.server.server_port}/")

        await notifier.send("Test Subject", "Test Body")

        assert server.received == [{"subject": "Test Subject", "body": "Test Body"}]


async def test_webhook_notifier_raises_when_server_returns_an_error_status() -> None:
    with recording_http_server(port=18582, response_status=500) as server:
        notifier = WebhookNotifier(f"http://127.0.0.1:{server.server.server_port}/")

        with pytest.raises(urllib.error.HTTPError):
            await notifier.send("Test Subject", "Test Body")


async def test_webhook_notifier_raises_when_the_server_is_unreachable() -> None:
    notifier = WebhookNotifier("http://127.0.0.1:18583/", timeout_seconds=1.0)

    with pytest.raises(urllib.error.URLError):
        await notifier.send("Test Subject", "Test Body")
