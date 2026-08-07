from __future__ import annotations

from datetime import date

import httpx
import pytest

from macro_data.providers.fred import FredMacroProvider


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def _mock_response(observations: list[dict[str, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fred/series/observations"
        assert request.url.params["series_id"] == "T10Y2Y"
        assert request.url.params["api_key"] == "test-key"
        assert request.url.params["file_type"] == "json"
        return httpx.Response(200, json={"observations": observations})

    return httpx.MockTransport(handler)


def test_rejects_an_empty_api_key() -> None:
    with pytest.raises(ValueError):
        FredMacroProvider("")


async def test_fetch_series_parses_real_observations() -> None:
    transport = _mock_response(
        [
            {"date": "2026-01-02", "value": "0.45"},
            {"date": "2026-01-01", "value": "0.42"},
        ]
    )
    provider = FredMacroProvider("test-key", client=_client(transport))

    observations = await provider.fetch_series("T10Y2Y", limit=2)

    assert len(observations) == 2
    assert observations[0].series_id == "T10Y2Y"
    assert observations[0].observed_on == date(2026, 1, 2)
    assert observations[0].value == pytest.approx(0.45)
    assert observations[1].observed_on == date(2026, 1, 1)
    assert observations[1].value == pytest.approx(0.42)


async def test_fetch_series_treats_the_dot_placeholder_as_a_real_gap() -> None:
    transport = _mock_response([{"date": "2026-01-02", "value": "."}])
    provider = FredMacroProvider("test-key", client=_client(transport))

    observations = await provider.fetch_series("T10Y2Y")

    assert observations[0].value is None


async def test_fetch_series_rejects_invalid_arguments() -> None:
    provider = FredMacroProvider("test-key", client=_client(_mock_response([])))

    with pytest.raises(ValueError):
        await provider.fetch_series("")
    with pytest.raises(ValueError):
        await provider.fetch_series("T10Y2Y", limit=0)


async def test_fetch_series_raises_on_an_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error_message": "Bad Request"})

    provider = FredMacroProvider("bad-key", client=_client(httpx.MockTransport(handler)))

    with pytest.raises(httpx.HTTPStatusError):
        await provider.fetch_series("T10Y2Y")
