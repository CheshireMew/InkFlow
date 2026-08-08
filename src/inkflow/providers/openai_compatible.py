from __future__ import annotations

from typing import Any

import httpx

from inkflow.providers.base import ProviderCapabilities, ProviderError, ProviderResponse


class OpenAICompatibleProvider:
    name = "openai-compatible-chat"
    capabilities = ProviderCapabilities(web_search=False, structured_output=False)

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
        self.timeout_seconds = timeout_seconds

    async def complete(
        self, *, system: str, user: str, use_web_search: bool = False
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
            **self.parameters,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.base_url + "/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, "http error", str(exc)) from exc
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
        )
