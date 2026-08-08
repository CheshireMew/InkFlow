from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderCapabilities:
    web_search: bool = False
    structured_output: bool = False


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    raw: dict[str, Any]
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    name: str
    model: str
    capabilities: ProviderCapabilities

    async def complete(
        self, *, system: str, user: str, use_web_search: bool = False
    ) -> ProviderResponse: ...


class ProviderError(RuntimeError):
    def __init__(self, provider: str, kind: str, message: str) -> None:
        super().__init__(f"{provider} {kind}: {message}")
        self.provider = provider
        self.kind = kind
        self.message = message
