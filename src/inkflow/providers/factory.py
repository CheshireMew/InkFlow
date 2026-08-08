from __future__ import annotations

import os
from typing import Any

import keyring

from inkflow.providers.base import ModelProvider
from inkflow.providers.openai_compatible import OpenAICompatibleProvider
from inkflow.providers.openai_responses import OpenAIResponsesProvider
from inkflow.storage.schema import ProviderProfileRow

KEYRING_SERVICE = "InkFlow"


def save_api_key(secret_key_name: str, api_key: str) -> None:
    keyring.set_password(KEYRING_SERVICE, secret_key_name, api_key)


def load_api_key(profile: ProviderProfileRow) -> str:
    env_name = f"INKFLOW_API_KEY_{profile.name.upper().replace('-', '_').replace(' ', '_')}"
    value = os.environ.get(env_name) or os.environ.get("INKFLOW_API_KEY")
    if value:
        return value
    stored = keyring.get_password(KEYRING_SERVICE, profile.secret_key_name)
    if not stored:
        raise RuntimeError(f"API key is not configured for provider profile: {profile.name}")
    return stored


def create_provider(profile: ProviderProfileRow) -> ModelProvider:
    import json

    parameters: dict[str, Any] = json.loads(profile.parameters_json or "{}")
    kwargs = {
        "base_url": profile.base_url,
        "api_key": load_api_key(profile),
        "model": profile.model,
        "parameters": parameters,
    }
    if profile.adapter == "openai-compatible-chat":
        return OpenAICompatibleProvider(**kwargs)
    if profile.adapter == "openai-responses":
        return OpenAIResponsesProvider(**kwargs)
    raise ValueError(f"Unsupported provider adapter: {profile.adapter}")
