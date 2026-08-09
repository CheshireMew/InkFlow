from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReferenceKind(str, Enum):
    CASE = "case"
    HOOK = "hook"


class HandoffStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class JobKind(str, Enum):
    PREPARE_MATERIAL = "prepare_material"
    SELECT_REFERENCES = "select_references"
    GENERATE = "generate"


class PromptStage(str, Enum):
    PREPARE_MATERIAL = "prepare_material"
    SELECT_REFERENCES = "select_references"
    GENERATE = "generate"


class ExecutorKind(str, Enum):
    EXTERNAL = "external"
    API = "api"


class JobStatus(str, Enum):
    WAITING = "waiting"
    BLOCKED = "blocked"
    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class ExperimentKind(str, Enum):
    SINGLE = "single"
    BATCH_FIVE = "batch_five"
    COMPARE_RULES = "compare_rules"


class ExperimentStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewState(str, Enum):
    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class HandoffCore(BaseModel):
    """The approved writing input. Provenance never belongs in this model."""

    model_config = ConfigDict(extra="forbid")

    user_request: str
    purified_material: str
    reference_cases: list[str] = Field(default_factory=list)
    reference_hooks: list[str] = Field(default_factory=list)
    other_inputs: str = "无"

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_hash(self) -> str:
        return stable_hash(self.canonical_payload())


class ExecutionPackage(BaseModel):
    """The exact content visible to a generation model."""

    model_config = ConfigDict(extra="forbid")

    handoff: HandoffCore
    writing_rule: str

    def render(self) -> str:
        cases = "\n\n".join(item.strip() for item in self.handoff.reference_cases if item.strip())
        hooks = "\n\n".join(item.strip() for item in self.handoff.reference_hooks if item.strip())
        return "\n\n".join(
            [
                "【本次写作要求】\n" + self.handoff.user_request,
                "【写作规则】\n" + self.writing_rule.strip(),
                "【净化后材料】\n" + self.handoff.purified_material.strip(),
                "【参考写作案例】\n" + (cases or "本次未使用参考写作案例"),
                "【参考开头钩子】\n" + (hooks or "本次未使用参考开头钩子"),
                "【其它实际写作输入】\n" + (self.handoff.other_inputs.strip() or "无"),
            ]
        ).strip()

    def content_hash(self) -> str:
        return stable_hash(
            {
                "handoff_core_hash": self.handoff.content_hash(),
                "writing_rule": self.writing_rule,
            }
        )


class JobEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 2
    job_id: str
    attempt_id: str
    attempt: int
    lease_token: str
    kind: JobKind
    input_hash: str
    payload: dict[str, Any]


class DiscoveredSource(BaseModel):
    """One external source whose exact text contributed to prepared material."""

    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    content: str
    use: str

    @field_validator("title", "url", "content", "use")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("discovered source fields cannot be empty")
        return value.strip()


class PreparationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purified_material: str
    discovered_sources: list[DiscoveredSource] = Field(default_factory=list)
    other_inputs: str = "无"


class ReferenceSelectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_ids: list[str] = Field(default_factory=list)
    hook_ids: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs: list[str]


class ExternalExecutorMetadata(BaseModel):
    """Self-declared external runtime facts; never evidence of a controlled run."""

    model_config = ConfigDict(extra="forbid")

    runtime: str
    model: str
    runtime_version: str | None = None
    context_mode: Literal["fresh", "reused", "unknown"] = "unknown"
    tools: list[str] = Field(default_factory=list)

    @field_validator("runtime", "model")
    @classmethod
    def require_runtime_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("external runtime and model cannot be empty")
        return value.strip()


class ExternalGenerationResult(GenerationResult):
    executor_metadata: ExternalExecutorMetadata


class PromptDefinition(BaseModel):
    """The current prompt content before project data is rendered into it."""

    model_config = ConfigDict(extra="forbid")

    stage: PromptStage
    name: str
    system_prompt: str
    user_template: str
    contract_version: int = 1
    prompt_hash: str


class CurrentPrompt(BaseModel):
    """The current editable prompt and its file-backed index metadata."""

    model_config = ConfigDict(extra="forbid")

    stage: PromptStage
    name: str
    system_prompt: str
    user_template: str
    contract_version: int = 1
    prompt_hash: str
    current_file: str
    current_path: str
    origin: Literal["bundled", "user"]
    updated_at: str


class PromptSnapshot(BaseModel):
    """The exact prompt content and identity used by one job."""

    model_config = ConfigDict(extra="forbid")

    definition: PromptDefinition
    system_prompt: str
    user_prompt: str
    rendered_hash: str


class ProviderSnapshot(BaseModel):
    """Non-secret, immutable provider configuration captured for a run."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    revision: int
    adapter: str
    base_url: str
    model: str
    capabilities: dict[str, Any]
    parameters: dict[str, Any]
    config_hash: str


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
