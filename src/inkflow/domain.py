from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class ExecutorKind(str, Enum):
    EXTERNAL = "external"
    API = "api"


class JobStatus(str, Enum):
    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
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
                "【本次写作要求】\n" + self.handoff.user_request.strip(),
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
    schema_version: int = 1
    job_id: str
    lease_token: str
    kind: JobKind
    input_hash: str
    payload: dict[str, Any]


class PreparationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purified_material: str
    discovered_sources: list[dict[str, str]] = Field(default_factory=list)
    other_inputs: str = "无"


class ReferenceSelectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_ids: list[str] = Field(default_factory=list)
    hook_ids: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs: list[str]
    raw_response: str | None = None
    executor_metadata: dict[str, Any] = Field(default_factory=dict)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
