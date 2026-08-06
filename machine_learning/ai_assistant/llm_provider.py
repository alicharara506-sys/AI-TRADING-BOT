from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-agnostic interface for a text-generating LLM backend.

    Claude, OpenAI, Gemini, DeepSeek, a local model, or any future vendor
    implements exactly this and nothing more: text in, text out.
    Deliberately dumb -- no structured-output contract lives on this
    Protocol, so swapping vendors never means rewriting parsing logic too
    (see opinion.py for that layer, which is provider-independent).

    Research finding this directly addresses: danilobatson/ai-trading-agent-gemini
    hardcoded `GoogleGenerativeAI` instantiation directly inside its signal
    generator with no interface in between, making every other provider a
    full rewrite rather than a new implementation of a shared contract.
    """

    async def generate(self, prompt: str) -> str: ...


__all__ = ["LLMProvider"]
