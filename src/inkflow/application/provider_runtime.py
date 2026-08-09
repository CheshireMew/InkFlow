from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict

from inkflow.domain import ExecutorKind
from inkflow.prompt_entities import read_operational_prompt
from inkflow.providers.base import ProviderResponse
from inkflow.providers.factory import create_provider, delete_api_key, save_api_key
from inkflow.runtime_logging import log_ai_event
from inkflow.storage import ProviderStore
from inkflow.storage.common import new_id
from inkflow.structured_data import parse_model_json


class ProviderRuntime:
    def __init__(self, providers: ProviderStore) -> None:
        self.providers = providers

    def configure(
        self,
        *,
        name: str,
        adapter: str,
        base_url: str,
        model: str,
        api_key: str,
        parameters: dict[str, Any],
        activate: bool,
    ) -> str:
        if adapter not in {"openai-compatible-chat", "openai-responses"}:
            raise ValueError(f"unsupported provider adapter: {adapter}")
        profile_id = new_id("provider")
        secret_key_name = f"provider:{profile_id}"
        save_api_key(secret_key_name, api_key)
        capabilities = {
            "web_search": adapter == "openai-responses",
            "structured_output": True,
        }
        try:
            row = self.providers.add(
                profile_id=profile_id,
                name=name,
                adapter=adapter,
                base_url=base_url,
                model=model,
                capabilities=capabilities,
                parameters=parameters,
                secret_key_name=secret_key_name,
                activate=activate,
            )
        except Exception:
            delete_api_key(secret_key_name)
            raise
        return row.id

    async def test(self, profile_id: str | None = None) -> dict[str, Any]:
        profile = self.providers.get(profile_id)
        provider = create_provider(profile)
        prompt = read_operational_prompt("provider-test.prompt.json")
        response = await self.complete(
            provider,
            interaction=f"provider-test:{profile.id}",
            system=prompt.system_prompt,
            user=prompt.user_prompt,
            response_schema=_ProviderTestResult.model_json_schema(),
            use_web_search=False,
        )
        parsed = parse_model_json(response.content, _ProviderTestResult)
        return {
            "ok": parsed.ok,
            "provider_profile_id": profile.id,
            "provider": response.provider,
            "model": response.model,
            "usage": response.usage,
        }

    def validate_executor(
        self, executor: ExecutorKind, provider_profile_id: str | None
    ) -> None:
        if executor is ExecutorKind.EXTERNAL:
            if provider_profile_id is not None:
                raise ValueError(
                    "external execution cannot use an internal provider profile"
                )
            return
        self.providers.get(provider_profile_id)

    def snapshot(
        self, executor: ExecutorKind, provider_profile_id: str | None
    ) -> dict[str, Any]:
        if executor is ExecutorKind.EXTERNAL:
            return {}
        return self.providers.snapshot(
            self.providers.get(provider_profile_id)
        ).model_dump(mode="json")

    async def execute_snapshot(
        self,
        *,
        provider_snapshot: dict[str, Any],
        interaction: str,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        use_web_search: bool,
    ) -> ProviderResponse:
        profile = self.providers.get(provider_snapshot.get("id"))
        if profile.config_hash != provider_snapshot.get("config_hash"):
            raise RuntimeError(
                "provider profile snapshot no longer matches its immutable revision"
            )
        return await self.complete(
            create_provider(profile),
            interaction=interaction,
            system=system,
            user=user,
            response_schema=response_schema,
            use_web_search=use_web_search,
        )

    @staticmethod
    async def complete(
        provider,
        *,
        interaction: str,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        use_web_search: bool,
    ) -> ProviderResponse:
        log_ai_event(
            "request",
            interaction,
            executor="api",
            provider=getattr(provider, "name", type(provider).__name__),
            model=getattr(provider, "model", None),
            base_url=getattr(provider, "base_url", None),
            system_prompt=system,
            user_prompt=user,
            response_schema=response_schema,
        )
        started = time.perf_counter()
        try:
            response = await provider.complete(
                system=system,
                user=user,
                response_schema=response_schema,
                use_web_search=use_web_search,
            )
        except Exception as exc:
            log_ai_event(
                "response",
                interaction,
                executor="api",
                provider=getattr(provider, "name", type(provider).__name__),
                model=getattr(provider, "model", None),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                result="failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise
        log_ai_event(
            "response",
            interaction,
            executor="api",
            provider=response.provider,
            model=response.model,
            request_id=response.request_id,
            finish_reason=response.finish_reason,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            result="succeeded",
            usage=response.usage,
            model_content=response.content,
            raw_provider_response=response.raw,
        )
        return response


class _ProviderTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
