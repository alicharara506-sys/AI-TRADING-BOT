from __future__ import annotations

import json

import httpx
import pytest

from machine_learning.ai_assistant.ollama_llm_provider import OllamaLLMProvider


def _client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def test_rejects_empty_base_url_or_model() -> None:
    with pytest.raises(ValueError):
        OllamaLLMProvider(base_url="", model="llama3")
    with pytest.raises(ValueError):
        OllamaLLMProvider(base_url="http://localhost:11434", model="")


async def test_generate_posts_to_the_ollama_generate_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"response": "0.42"})

    provider = OllamaLLMProvider(
        base_url="http://localhost:11434",
        model="llama3",
        client=_client(httpx.MockTransport(handler)),
    )

    result = await provider.generate("rate sentiment")

    assert result == "0.42"
    assert captured["path"] == "/api/generate"
    assert captured["body"] == {"model": "llama3", "prompt": "rate sentiment", "stream": False}


async def test_generate_strips_trailing_slash_from_base_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "ok"})

    provider = OllamaLLMProvider(
        base_url="http://localhost:11434/",
        model="llama3",
        client=_client(httpx.MockTransport(handler)),
    )

    assert await provider.generate("x") == "ok"


async def test_generate_raises_on_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    provider = OllamaLLMProvider(
        base_url="http://localhost:11434",
        model="llama3",
        client=_client(httpx.MockTransport(handler)),
    )

    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate("x")
