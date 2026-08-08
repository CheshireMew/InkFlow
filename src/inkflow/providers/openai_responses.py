from __future__ import annotations

from typing import Any

import httpx

from inkflow.providers.base import ProviderCapabilities, ProviderError, ProviderResponse


class OpenAIResponsesProvider:
    name = "openai-responses"
    capabilities = ProviderCapabilities(web_search=True, structured_output=False)

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
        self.timeout_seconds = timeout_seconds

    async def complete(
        self, *, system: str, user: str, use_web_search: bool = False
    ) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": system,
            "input": user,
            **self.parameters,
        }
        if use_web_search:
            payload["tools"] = [{"type": "web_search"}]
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.base_url + "/responses",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, "http error", str(exc)) from exc
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
        )


def _extract_output_text(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip()
