from __future__ import annotations

import json

import pytest

from core.logging.setup import configure_logging, get_logger, set_correlation_id


def test_configure_logging_emits_json_with_correlation_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO")
    set_correlation_id("abc-123")
    logger = get_logger("test.logger")

    logger.info("hello")

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert payload["message"] == "hello"
    assert payload["correlation_id"] == "abc-123"
    assert payload["level"] == "INFO"

    set_correlation_id(None)
