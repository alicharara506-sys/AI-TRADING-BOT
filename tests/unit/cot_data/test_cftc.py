from __future__ import annotations

from datetime import date

import httpx
import pytest

from cot_data.providers.cftc import CftcCotProvider


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def _mock_response(rows: list[dict[str, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/resource/6dca-aqww.json"
        assert request.url.params["cftc_contract_market_code"] == "099741"
        assert request.url.params["$order"] == "report_date_as_yyyy_mm_dd DESC"
        return httpx.Response(200, json=rows)

    return httpx.MockTransport(handler)


async def test_fetch_observations_parses_real_rows() -> None:
    transport = _mock_response(
        [
            {
                "report_date_as_yyyy_mm_dd": "2026-01-06T00:00:00.000",
                "cftc_contract_market_code": "099741",
                "market_and_exchange_names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
                "noncomm_positions_long_all": "150000",
                "noncomm_positions_short_all": "90000",
                "comm_positions_long_all": "60000",
                "comm_positions_short_all": "120000",
                "open_interest_all": "700000",
            }
        ]
    )
    provider = CftcCotProvider(client=_client(transport))

    observations = await provider.fetch_observations("099741", limit=1)

    assert len(observations) == 1
    observation = observations[0]
    assert observation.report_date == date(2026, 1, 6)
    assert observation.contract_market_code == "099741"
    assert observation.market_and_exchange_name == "EURO FX - CHICAGO MERCANTILE EXCHANGE"
    assert observation.noncommercial_long == 150000
    assert observation.noncommercial_short == 90000
    assert observation.commercial_long == 60000
    assert observation.commercial_short == 120000
    assert observation.open_interest == 700000


async def test_fetch_observations_treats_a_missing_field_as_a_real_gap() -> None:
    transport = _mock_response(
        [
            {
                "report_date_as_yyyy_mm_dd": "2026-01-06T00:00:00.000",
                "cftc_contract_market_code": "099741",
                "market_and_exchange_names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
                "open_interest_all": "700000",
            }
        ]
    )
    provider = CftcCotProvider(client=_client(transport))

    observations = await provider.fetch_observations("099741")

    assert observations[0].noncommercial_long is None
    assert observations[0].noncommercial_short is None
    assert observations[0].commercial_long is None
    assert observations[0].commercial_short is None
    assert observations[0].open_interest == 700000


async def test_fetch_observations_rejects_invalid_arguments() -> None:
    provider = CftcCotProvider(client=_client(_mock_response([])))

    with pytest.raises(ValueError):
        await provider.fetch_observations("")
    with pytest.raises(ValueError):
        await provider.fetch_observations("099741", limit=0)


async def test_fetch_observations_raises_on_an_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "Internal error"})

    provider = CftcCotProvider(client=_client(httpx.MockTransport(handler)))

    with pytest.raises(httpx.HTTPStatusError):
        await provider.fetch_observations("099741")
