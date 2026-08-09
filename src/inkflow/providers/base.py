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
    request_id: str | None = None
    finish_reason: str | None = None


class ModelProvider(Protocol):
    name: str
    model: str
    capabilities: ProviderCapabilities

    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        use_web_search: bool = False,
    ) -> ProviderResponse: ...


class ProviderError(RuntimeError):
    def __init__(self, provider: str, kind: str, message: str) -> None:
        super().__init__(f"{provider} {kind}: {message}")
        self.provider = provider
        self.kind = kind
        self.message = message


def openai_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    def normalize(value: Any) -> Any:
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {
            key: normalize(item)
            for key, item in value.items()
            if key not in {"default"}
        }
        properties = result.get("properties")
        if result.get("type") == "object" and isinstance(properties, dict):
            result["additionalProperties"] = False
            result["required"] = list(properties)
        return result

    return normalize(schema)
