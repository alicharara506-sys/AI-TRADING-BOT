from __future__ import annotations

import httpx

_GENERATE_PATH = "/api/generate"
_DEFAULT_TIMEOUT_SECONDS = 30.0


class OllamaLLMProvider:
    """LLMProvider (machine_learning/ai_assistant/llm_provider.py)
    satisfied against a local Ollama server (https://ollama.com -- free,
    runs entirely on your own machine at e.g. http://localhost:11434, no
    API key, no per-token cost, no network call beyond localhost).
    Structurally satisfies the LLMProvider Protocol the same way every
    other implementation does (text in, text out); nothing about Ollama
    specifically leaks past this one class -- LLMBackedReviewer,
    LocalLLMConsensusEngine, or any other LLMProvider consumer works with
    this exactly like it would with a cloud vendor's implementation.

    Follows this platform's established real-HTTP-client pattern
    (macro_data/providers/fred.py, cot_data/providers/cftc.py): an
    injectable httpx.AsyncClient so tests exercise the real request/parse
    logic against a mocked transport rather than a hand-rolled fake.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not base_url:
            raise ValueError("base_url must not be empty")
        if not model:
            raise ValueError("model must not be empty")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def generate(self, prompt: str) -> str:
        response = await self._client.post(
            f"{self._base_url}{_GENERATE_PATH}",
            json={"model": self._model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["response"])


__all__ = ["OllamaLLMProvider"]
