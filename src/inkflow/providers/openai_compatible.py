from __future__ import annotations

from typing import Any

from inkflow.providers.base import (
    ProviderCapabilities,
    ProviderError,
    ProviderResponse,
    openai_strict_schema,
)
from inkflow.providers.http_boundary import post_json


class OpenAICompatibleProvider:
    name = "openai-compatible-chat"
    capabilities = ProviderCapabilities(web_search=False, structured_output=True)

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        parameters: dict[str, Any] | None = None,
        timeout_seconds: float = 90,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.parameters = parameters or {}
        reserved = {"model", "messages", "stream", "response_format"}
        if reserved & self.parameters.keys():
            names = ", ".join(sorted(reserved & self.parameters.keys()))
            raise ValueError(f"provider parameters cannot override protocol fields: {names}")
        self.timeout_seconds = timeout_seconds

    async def complete(
        self,
        *,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        use_web_search: bool = False,
    ) -> ProviderResponse:
        if use_web_search:
            raise ProviderError(self.name, "unsupported capability", "web search is not available")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "inkflow_result",
                    "strict": True,
                    "schema": openai_strict_schema(response_schema),
                },
            },
            **self.parameters,
        }
        data, request_id = await post_json(
            provider=self.name,
            url=self.base_url + "/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(self.name, "empty response", "provider returned no choices")
        content = str((choices[0].get("message") or {}).get("content") or "").strip()
        return ProviderResponse(
            content=content,
            raw=data,
            provider=self.name,
            model=self.model,
            usage=data.get("usage") or {},
            request_id=request_id,
            finish_reason=str(choices[0].get("finish_reason") or "") or None,
        )
