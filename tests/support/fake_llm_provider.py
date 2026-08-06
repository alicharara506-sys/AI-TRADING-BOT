from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeLLMProvider:
    """Configurable LLMProvider test double. Set `next_response` to control
    what generate() returns, or `error` to simulate a provider failure --
    network error, auth failure, rate limit, timeout all look the same from
    the caller's side: an exception raised out of generate().
    """

    next_response: str = ""
    error: Exception | None = None
    prompts_received: list[str] = field(default_factory=list)

    async def generate(self, prompt: str) -> str:
        self.prompts_received.append(prompt)
        if self.error is not None:
            raise self.error
        return self.next_response


__all__ = ["FakeLLMProvider"]
