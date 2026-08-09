from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from inkflow.domain import ExecutorKind, HandoffCore, JobStatus, PromptStage
from inkflow.providers.base import ProviderCapabilities, ProviderResponse
from inkflow.service import InkFlowService
from inkflow.storage import Database
from inkflow.structured_data import StructuredResultError


def make_service(tmp_path: Path) -> InkFlowService:
    return InkFlowService(Database(tmp_path / "inkflow.sqlite3"))


def test_external_lease_is_atomic_and_retry_creates_a_distinct_attempt(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.create_project(
        title="并发领取", user_request="原样写作要求", materials=[("", "材料")]
    )
    job_id = service.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)

    with ThreadPoolExecutor(max_workers=2) as pool:
        leased = list(pool.map(lambda _: service.lease_external_job(project_id), range(2)))
    envelopes = [item for item in leased if item is not None]
    assert len(envelopes) == 1
    first = envelopes[0]
    assert first.job_id == job_id
    assert first.attempt == 1

    service.retry_job(job_id)
    second = service.lease_external_job(project_id)
    assert second is not None
    assert second.attempt == 2
    assert second.attempt_id != first.attempt_id
    attempts = service.workflows.list_attempts(job_id)
    assert [item.status for item in attempts] == [JobStatus.FAILED.value, JobStatus.LEASED.value]


def test_prompt_revision_is_snapshotted_before_the_chain_runs(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.create_project(
        title="提示词快照", user_request="不要改写这句话\n", materials=[("", "材料")]
    )
    original = service.prompts.get(stage=PromptStage.PREPARE_MATERIAL)
    job_id = service.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    replacement = service.add_prompt(
        stage=PromptStage.PREPARE_MATERIAL,
        name="新版净化",
        system_prompt="只保留材料中的事实。",
        user_template="要求：{{user_request}}\n材料：{{materials}}",
        activate=True,
    )
    envelope = service.lease_external_job(project_id)
    assert envelope is not None and envelope.job_id == job_id
    snapshot = envelope.payload["prompt_snapshot"]["definition"]
    assert snapshot["id"] == original.id
    assert snapshot["prompt_hash"] == original.prompt_hash
    assert snapshot["id"] != replacement.id
    assert "不要改写这句话\n" in envelope.payload["prompt_snapshot"]["user_prompt"]


def test_invalid_api_json_preserves_raw_response_and_format_error(
    monkeypatch, tmp_path: Path
) -> None:
    service = make_service(tmp_path)
    service.providers.add(
        profile_id="provider-invalid-json",
        name="invalid-json",
        adapter="openai-responses",
        base_url="https://provider.invalid/v1",
        model="fake-model",
        capabilities={"web_search": True},
        parameters={},
        secret_key_name="unused",
        activate=True,
    )

    class InvalidProvider:
        capabilities = ProviderCapabilities(web_search=True)

        async def complete(self, **_kwargs):
            return ProviderResponse(
                content='{"purified_material": "材料", "purified_material": "重复键"}',
                raw={},
                provider="fake",
                model="fake-model",
            )

    monkeypatch.setattr("inkflow.service.create_provider", lambda _profile: InvalidProvider())
    project_id = service.create_project(
        title="格式失败", user_request="写作", materials=[("", "材料")]
    )
    job_id = service.start_preparation(project_id, executor=ExecutorKind.API)
    with pytest.raises(StructuredResultError, match="duplicate JSON key"):
        asyncio.run(service.run_api_jobs(project_id))
    job = service.workflows.get_job(job_id)
    attempt = service.workflows.list_attempts(job_id)[0]
    assert job.status == JobStatus.FAILED.value
    assert attempt.raw_response == (
        '{"purified_material": "材料", "purified_material": "重复键"}'
    )
    assert "duplicate JSON key" in str(attempt.format_error)


def test_result_edits_are_versions_and_model_output_stays_immutable(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.create_project(
        title="编辑版本", user_request="写作", materials=[("", "材料")]
    )
    rule = service.add_rule(name="规则", body="直接写。", activate=True)
    service.workflows.create_handoff_revision(
        project_id=project_id,
        core=HandoffCore(user_request="写作", purified_material="材料"),
        case_ids=[],
        hook_ids=[],
    )
    service.approve_handoff(project_id)
    service.start_generation(project_id, executor=ExecutorKind.EXTERNAL, rule_id=rule.id)
    envelope = service.lease_external_job(project_id)
    assert envelope is not None
    service.submit_job_result(
        envelope.job_id,
        attempt_id=envelope.attempt_id,
        lease_token=envelope.lease_token,
        raw_response=json.dumps({"outputs": ["模型原文"]}, ensure_ascii=False),
    )
    generation = service.results.list(project_id)[0]
    service.results.add_revision(generation.id, "人工第一版")
    service.results.add_revision(generation.id, "人工第二版")
    assert service.results.get(generation.id).content == "模型原文"
    assert service.results.current_content(generation.id) == "人工第二版"
    assert [item.revision for item in service.results.list_revisions(generation.id)] == [1, 2]


def test_new_source_invalidates_current_handoff_but_keeps_history(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.create_project(
        title="材料变化", user_request="写作", materials=[("", "原材料")]
    )
    handoff = service.workflows.create_handoff_revision(
        project_id=project_id,
        core=HandoffCore(user_request="写作", purified_material="原材料"),
        case_ids=[],
        hook_ids=[],
    )
    service.approve_handoff(project_id)
    service.add_rule(name="规则", body="直接写。", activate=True)

    service.add_source(project_id, content="新增事实", kind="pasted", provenance={})

    history = service.workflows.list_handoffs(project_id)
    assert len(history) == 1
    assert history[0].id == handoff.id
    assert history[0].status == "superseded"
    with pytest.raises(FileNotFoundError, match="Handoff not found"):
        service.start_generation(project_id, executor=ExecutorKind.EXTERNAL)
