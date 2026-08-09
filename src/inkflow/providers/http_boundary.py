from __future__ import annotations

from typing import Any

import httpx

from inkflow.providers.base import ProviderError
from inkflow.structured_data import StructuredResultError, parse_json_object

MAX_PROVIDER_RESPONSE_BYTES = 4 * 1024 * 1024


async def post_json(
    *,
    provider: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> tuple[dict[str, Any], str | None]:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_PROVIDER_RESPONSE_BYTES:
                        raise ProviderError(
                            provider,
                            "response too large",
                            f"provider response exceeds {MAX_PROVIDER_RESPONSE_BYTES} bytes",
                        )
                request_id = response.headers.get("x-request-id")
    except ProviderError:
        raise
    except httpx.HTTPError as exc:
        raise ProviderError(provider, "http error", str(exc)) from exc
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProviderError(provider, "invalid response", "response is not UTF-8") from exc
    try:
        data = parse_json_object(
            text,
            boundary=f"{provider} response",
            max_bytes=MAX_PROVIDER_RESPONSE_BYTES,
        )
    except StructuredResultError as exc:
        raise ProviderError(provider, exc.code, str(exc)) from exc
    return data, request_id
