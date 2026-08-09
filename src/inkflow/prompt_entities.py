from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from inkflow.domain import PromptStage
from inkflow.resources import prompt_files


class PromptEntity(BaseModel):
    """A human-editable, immutable prompt revision stored as one physical file."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str
    stage: PromptStage
    name: str
    system_prompt: str
    user_template: str
    contract_version: int = 1
    revision: int | None = None
    default_active: bool = False
    source: dict[str, Any] = Field(default_factory=dict)


class OperationalPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    name: str
    system_prompt: str
    user_prompt: str


class SpecializedPromptEntity(BaseModel):
    """A physical prompt kept for a specialized workflow outside the three writing stages."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    id: str
    name: str
    purpose: Literal[
        "ai_flavor_audit_and_cleanup",
        "ai_flavor_guidance",
        "content_audit_guidance",
        "writing_guidance",
    ]
    system_prompt: str
    user_template: str
    source: dict[str, Any] = Field(default_factory=dict)


def bundled_prompt_entities() -> list[tuple[Path, PromptEntity]]:
    root = prompt_files() / "seeds"
    entities = [(path, read_prompt_entity(path)) for path in sorted(root.rglob("*.prompt.json"))]
    if not entities:
        raise RuntimeError(f"no bundled prompt entity files found in {root}")
    defaults: dict[PromptStage, int] = {stage: 0 for stage in PromptStage}
    for _path, entity in entities:
        if entity.default_active:
            defaults[entity.stage] += 1
    invalid = [stage.value for stage, count in defaults.items() if count != 1]
    if invalid:
        raise RuntimeError(
            "bundled prompts must contain exactly one default per stage: " + ", ".join(invalid)
        )
    return entities


def default_bundled_prompts() -> dict[PromptStage, PromptEntity]:
    return {
        entity.stage: entity for _path, entity in bundled_prompt_entities() if entity.default_active
    }


def read_prompt_entity(path: Path) -> PromptEntity:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read prompt entity file {path}: {exc}") from exc
    return PromptEntity.model_validate(payload)


def read_operational_prompt(name: str) -> OperationalPrompt:
    path = prompt_files() / "operations" / name
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read operational prompt file {path}: {exc}") from exc
    return OperationalPrompt.model_validate(payload)


def bundled_specialized_prompts() -> list[tuple[Path, SpecializedPromptEntity]]:
    root = prompt_files() / "library" / "ai_flavor"
    prompts: list[tuple[Path, SpecializedPromptEntity]] = []
    for path in sorted(root.rglob("*.prompt.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot read specialized prompt file {path}: {exc}") from exc
        prompts.append((path, SpecializedPromptEntity.model_validate(payload)))
    if not prompts:
        raise RuntimeError(f"no AI-flavor prompt files found in {root}")
    return prompts


def write_prompt_entity(path: Path, entity: PromptEntity) -> None:
    """Create an entity file once. Existing prompt revisions are never overwritten."""

    encoded = json.dumps(entity.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8-sig") != encoded:
            raise RuntimeError(f"prompt entity file is immutable and differs from index: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def write_editable_prompt(path: Path, entity: PromptEntity) -> None:
    """Refresh the one user-editable working file for a stage after preserving its revision."""

    encoded = json.dumps(entity.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8-sig") == encoded:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)
