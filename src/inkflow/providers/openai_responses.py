from __future__ import annotations

from typing import Any

from inkflow.providers.base import (
    ProviderCapabilities,
    ProviderError,
    ProviderResponse,
    openai_strict_schema,
)
from inkflow.providers.http_boundary import post_json


class OpenAIResponsesProvider:
    name = "openai-responses"
    capabilities = ProviderCapabilities(web_search=True, structured_output=True)

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        parameters: dict[str, Any] | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.parameters = parameters or {}
        reserved = {"model", "instructions", "input", "text", "tools"}
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
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": system,
            "input": user,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "inkflow_result",
                    "strict": True,
                    "schema": openai_strict_schema(response_schema),
                }
            },
            **self.parameters,
        }
        if use_web_search:
            payload["tools"] = [{"type": "web_search"}]
        data, request_id = await post_json(
            provider=self.name,
            url=self.base_url + "/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        content = str(data.get("output_text") or "").strip()
        if not content:
            content = _extract_output_text(data)
        if not content:
            raise ProviderError(self.name, "empty response", "provider returned no output text")
        return ProviderResponse(
            content=content,
            raw=data,
            provider=self.name,
            model=self.model,
            usage=data.get("usage") or {},
            request_id=request_id,
            finish_reason=str(data.get("status") or "") or None,
        )


def _extract_output_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip()
