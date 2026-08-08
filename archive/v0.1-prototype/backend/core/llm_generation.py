import json
import logging
import re
from typing import Any

from core.writing_contract import (
    build_rewrite_prompt,
    cleanup_text,
    review_text,
)
from services.llm_service import LLMService

logger = logging.getLogger("LLMGeneration")

MODEL_MAP = {
    "DeepSeek V3 (Fast)": "deepseek-chat",
    "DeepSeek R1 (Reasoning)": "deepseek-reasoner",
    "GPT-4o (Premium)": "gpt-4o",
}


def resolve_model_override(render_context: dict[str, Any]) -> str | None:
    for value in render_context.values():
        found_name = _extract_model_name(value)
        if not found_name:
            continue

        model_override = MODEL_MAP.get(found_name)
        if model_override:
            logger.info("🔀 Switching model to: %s (User selected: %s)", model_override, found_name)
            return model_override
    return None


async def generate_variants(
    *,
    service: LLMService,
    system_prompt: str,
    user_prompt: str,
    output_format: str,
    temperature: float,
    model_override: str | None,
) -> list[Any]:
    if output_format == "json":
        content = await service.generate_content(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            model=model_override,
        )
        return parse_json_variants(content)

    return await service.generate_variants(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        n=3,
        temperature=temperature,
        model=model_override,
    )


def parse_json_variants(content: str) -> list[Any]:
    json_match = re.search(r"\[.*\]", content, re.DOTALL)
    content_str = json_match.group(0) if json_match else content

    try:
        parsed = json.loads(content_str)
        if isinstance(parsed, list):
            return parsed
        return [str(parsed)]
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON output: %s", content)
        return [content]


async def enforce_writing_contract(
    *,
    variants: list[Any],
    contract,
    service: LLMService,
    system_prompt: str,
    model_override: str | None,
) -> list[Any]:
    processed: list[Any] = []
    for variant in variants:
        if isinstance(variant, dict):
            cleaned = await rewrite_until_pass(
                content=str(variant.get("content", "")),
                contract=contract,
                service=service,
                system_prompt=system_prompt,
                model_override=model_override,
            )
            processed.append({**variant, "content": cleaned})
            continue

        cleaned = await rewrite_until_pass(
            content=str(variant),
            contract=contract,
            service=service,
            system_prompt=system_prompt,
            model_override=model_override,
        )
        processed.append(cleaned)
    return processed


async def rewrite_until_pass(
    *,
    content: str,
    contract,
    service: LLMService,
    system_prompt: str,
    model_override: str | None,
) -> str:
    current = cleanup_text(content, contract)
    report = review_text(current, contract)

    attempts = 0
    while not report.passed and attempts < contract.rewrite_attempts:
        rewrite_prompt = build_rewrite_prompt(current, report)
        current = await service.generate_content(
            system_prompt=system_prompt,
            user_prompt=rewrite_prompt,
            temperature=0.6,
            model=model_override,
        )
        current = cleanup_text(current, contract)
        report = review_text(current, contract)
        attempts += 1

    return cleanup_text(current, contract)


def _extract_model_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("llm_model")
    if hasattr(value, "get"):
        return value.get("llm_model")
    return getattr(value, "llm_model", None)
