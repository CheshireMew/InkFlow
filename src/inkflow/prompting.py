from __future__ import annotations

import json
import re
from typing import Any

from inkflow.domain import (
    GenerationResult,
    PreparationResult,
    PromptDefinition,
    PromptSnapshot,
    PromptStage,
    ReferenceSelectionResult,
    stable_hash,
)
from inkflow.resources import prompt_files

PLACEHOLDER = re.compile(r"{{\s*([a-z_]+)\s*}}")


REQUIRED_PLACEHOLDERS: dict[PromptStage, set[str]] = {
    PromptStage.PREPARE_MATERIAL: {"user_request", "materials"},
    PromptStage.SELECT_REFERENCES: {"user_request", "purified_material", "reference_index"},
    PromptStage.GENERATE: {"execution_package"},
}


def validate_prompt_template(stage: PromptStage, system_prompt: str, user_template: str) -> None:
    if not system_prompt.strip():
        raise ValueError("system_prompt cannot be empty")
    if not user_template.strip():
        raise ValueError("user_template cannot be empty")
    found = set(PLACEHOLDER.findall(user_template))
    required = REQUIRED_PLACEHOLDERS[stage]
    missing = required - found
    unknown = found - required
    if missing:
        raise ValueError(f"prompt template is missing placeholders: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"prompt template has unknown placeholders: {', '.join(sorted(unknown))}")


def prompt_hash(
    stage: PromptStage,
    system_prompt: str,
    user_template: str,
    *,
    contract_version: int = 1,
) -> str:
    validate_prompt_template(stage, system_prompt, user_template)
    return stable_hash(
        {
            "stage": stage.value,
            "system_prompt": system_prompt,
            "user_template": user_template,
            "contract_version": contract_version,
        }
    )


def render_prompt(
    definition: PromptDefinition,
    context: dict[str, Any],
    *,
    output_count: int = 1,
) -> PromptSnapshot:
    validate_prompt_template(definition.stage, definition.system_prompt, definition.user_template)
    required = REQUIRED_PLACEHOLDERS[definition.stage]
    missing_context = required - context.keys()
    if missing_context:
        raise ValueError(f"prompt context is missing: {', '.join(sorted(missing_context))}")

    def replace(match: re.Match[str]) -> str:
        value = context[match.group(1)]
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)

    user_prompt = PLACEHOLDER.sub(replace, definition.user_template)
    system_prompt = (
        definition.system_prompt.rstrip()
        + "\n\n"
        + _locked_contract(definition.stage, output_count)
    )
    return PromptSnapshot(
        definition=definition,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        rendered_hash=stable_hash(
            {
                "definition_hash": definition.prompt_hash,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        ),
    )


def _locked_contract(stage: PromptStage, output_count: int) -> str:
    if stage is PromptStage.PREPARE_MATERIAL:
        schema = PreparationResult.model_json_schema()
    elif stage is PromptStage.SELECT_REFERENCES:
        schema = ReferenceSelectionResult.model_json_schema()
    else:
        if output_count < 1:
            raise ValueError("output_count must be positive")
        schema = GenerationResult.model_json_schema()
    contract_name = f"{stage.value}.txt"
    if stage is PromptStage.GENERATE and output_count > 1:
        contract_name = "generate_many.txt"
    contract_path = prompt_files() / "contracts" / contract_name
    try:
        template = contract_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RuntimeError(f"cannot read prompt contract file {contract_path}: {exc}") from exc
    return (
        template.replace(
            "{{result_schema}}", json.dumps(schema, ensure_ascii=False, sort_keys=True)
        )
        .replace("{{output_count}}", str(output_count))
        .strip()
    )
