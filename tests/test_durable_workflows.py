from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from inkflow.domain import ExecutorKind, HandoffCore, JobStatus, PromptStage, ReviewState
from inkflow.providers.base import ProviderCapabilities, ProviderResponse
from inkflow.service import InkFlowService
from inkflow.storage import Database
from inkflow.structured_data import StructuredResultError


def make_service(tmp_path: Path) -> InkFlowService:
    return InkFlowService(Database(tmp_path / "inkflow.sqlite3"))


def test_external_lease_is_atomic_and_retry_creates_a_distinct_attempt(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="并发领取", user_request="原样写作要求", materials=[("", "材料")]
    )
    job_id = service.jobs.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)

    with ThreadPoolExecutor(max_workers=2) as pool:
        leased = list(pool.map(lambda _: service.jobs.lease_external(project_id), range(2)))
    envelopes = [item for item in leased if item is not None]
    assert len(envelopes) == 1
    first = envelopes[0]
    assert first.job_id == job_id
    assert first.attempt == 1

    service.jobs.retry(job_id)
    second = service.jobs.lease_external(project_id)
    assert second is not None
    assert second.attempt == 2
    assert second.attempt_id != first.attempt_id
    attempts = service.workflows.list_attempts(job_id)
    assert [item.status for item in attempts] == [JobStatus.FAILED.value, JobStatus.LEASED.value]


def test_current_prompt_is_snapshotted_before_the_chain_runs(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="提示词快照", user_request="不要改写这句话\n", materials=[("", "材料")]
    )
    original = service.prompts.get(PromptStage.PREPARE_MATERIAL)
    job_id = service.jobs.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    replacement = service.prompts.save(
        stage=PromptStage.PREPARE_MATERIAL,
        name="新版净化",
        system_prompt="只保留材料中的事实。",
        user_template="要求：{{user_request}}\n材料：{{materials}}",
    )
    envelope = service.jobs.lease_external(project_id)
    assert envelope is not None and envelope.job_id == job_id
    snapshot = envelope.payload["prompt_snapshot"]["definition"]
    assert snapshot["prompt_hash"] == original.prompt_hash
    assert snapshot["prompt_hash"] != replacement.prompt_hash
    assert snapshot["system_prompt"] == original.system_prompt
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

    monkeypatch.setattr(
        "inkflow.application.provider_runtime.create_provider",
        lambda _profile: InvalidProvider(),
    )
    project_id = service.project_inputs.create_project(
        title="格式失败", user_request="写作", materials=[("", "材料")]
    )
    job_id = service.jobs.start_preparation(project_id, executor=ExecutorKind.API)
    with pytest.raises(StructuredResultError, match="duplicate JSON key"):
        asyncio.run(service.jobs.run_api_jobs(project_id))
    job = service.workflows.get_job(job_id)
    attempt = service.workflows.list_attempts(job_id)[0]
    assert job.status == JobStatus.FAILED.value
    assert attempt.raw_response == (
        '{"purified_material": "材料", "purified_material": "重复键"}'
    )
    assert "duplicate JSON key" in str(attempt.format_error)


def test_result_edits_are_versions_and_model_output_stays_immutable(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="编辑版本", user_request="写作", materials=[("", "材料")]
    )
    rule = service.library.add_rule(name="规则", body="直接写。", activate=True)
    service.workflows.create_handoff_revision(
        project_id=project_id,
        core=HandoffCore(user_request="写作", purified_material="材料"),
        case_ids=[],
        hook_ids=[],
    )
    service.handoffs.approve(project_id)
    service.experiments.start_generation(
        project_id, executor=ExecutorKind.EXTERNAL, rule_id=rule.id
    )
    envelope = service.jobs.lease_external(project_id)
    assert envelope is not None
    service.jobs.submit_result(
        envelope.job_id,
        attempt_id=envelope.attempt_id,
        lease_token=envelope.lease_token,
        raw_response=json.dumps(
            {
                "outputs": ["模型原文"],
                "executor_metadata": {
                    "runtime": "pytest-external",
                    "model": "test-model",
                    "context_mode": "fresh",
                    "tools": [],
                },
            },
            ensure_ascii=False,
        ),
    )
    generation = service.results.list(project_id)[0]
    assert generation.review_state == ReviewState.UNREVIEWED.value
    service.results.review(generation.id, ReviewState.ACCEPTED)
    assert service.results.get(generation.id).review_state == ReviewState.ACCEPTED.value
    service.results.add_revision(generation.id, "人工第一版")
    assert service.results.get(generation.id).review_state == ReviewState.UNREVIEWED.value
    service.results.add_revision(generation.id, "人工第二版")
    assert service.results.get(generation.id).content == "模型原文"
    assert service.results.current_content(generation.id) == "人工第二版"
    assert [item.revision for item in service.results.list_revisions(generation.id)] == [1, 2]


def test_new_source_invalidates_current_handoff_but_keeps_history(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="材料变化", user_request="写作", materials=[("", "原材料")]
    )
    handoff = service.workflows.create_handoff_revision(
        project_id=project_id,
        core=HandoffCore(user_request="写作", purified_material="原材料"),
        case_ids=[],
        hook_ids=[],
    )
    service.handoffs.approve(project_id)
    service.library.add_rule(name="规则", body="直接写。", activate=True)

    service.project_inputs.add_source(project_id, content="新增事实", kind="pasted", provenance={})

    history = service.workflows.list_handoffs(project_id)
    assert len(history) == 1
    assert history[0].id == handoff.id
    assert history[0].status == "superseded"
    with pytest.raises(FileNotFoundError, match="Handoff not found"):
        service.experiments.start_generation(project_id, executor=ExecutorKind.EXTERNAL)


def test_source_edit_invalidates_the_current_handoff_and_preserves_history(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="素材修订", user_request="写作", materials=[("", "旧素材")]
    )
    source = service.projects.list_sources(project_id)[0]
    handoff = service.workflows.create_handoff_revision(
        project_id=project_id,
        core=HandoffCore(user_request="写作", purified_material="旧素材"),
        case_ids=[],
        hook_ids=[],
    )
    service.handoffs.approve(project_id)

    service.project_inputs.update_source(project_id, source.id, "修订后的完整素材")

    with pytest.raises(FileNotFoundError, match="Handoff not found"):
        service.workflows.get_handoff(project_id)
    history = service.workflows.list_handoffs(project_id)
    assert [(item.id, item.status) for item in history] == [
        (handoff.id, "superseded")
    ]
    assert service.projects.list_sources(project_id)[0].content == "修订后的完整素材"


def test_project_input_change_supersedes_an_active_preparation_attempt(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="输入修订", user_request="旧要求", materials=[("", "旧材料")]
    )
    job_id = service.jobs.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    envelope = service.jobs.lease_external(project_id)
    assert envelope is not None

    service.project_inputs.add_source(project_id, content="新材料", kind="pasted", provenance={})

    job = service.workflows.get_job(job_id)
    attempt = service.workflows.list_attempts(job_id)[0]
    assert job.status == JobStatus.SUPERSEDED.value
    assert attempt.status == JobStatus.SUPERSEDED.value
    with pytest.raises(ValueError, match="no longer completable"):
        service.jobs.submit_result(
            job_id,
            attempt_id=envelope.attempt_id,
            lease_token=envelope.lease_token,
            raw_response=json.dumps(
                {
                    "purified_material": "旧材料",
                    "discovered_sources": [],
                    "other_inputs": "无",
                },
                ensure_ascii=False,
            ),
        )
    jobs = service.workflows.list_jobs(project_id)
    assert [(item.id, item.status) for item in jobs] == [
        (job.id, JobStatus.SUPERSEDED.value)
    ]
    assert service.workflows.list_handoffs(project_id) == []


def test_only_one_preparation_chain_can_be_active(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="单准备链", user_request="写作", materials=[("", "材料")]
    )
    first = service.jobs.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)

    with pytest.raises(ValueError, match="active preparation chain"):
        service.jobs.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)

    assert [job.id for job in service.workflows.list_jobs(project_id)] == [first]


def test_concurrent_preparation_requests_share_the_atomic_creation_boundary(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="并发单准备链", user_request="写作", materials=[("", "材料")]
    )

    def start() -> str:
        try:
            return service.jobs.start_preparation(
                project_id, executor=ExecutorKind.EXTERNAL
            )
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: start(), range(2)))

    assert len(service.workflows.list_jobs(project_id)) == 1
    assert sum(item.startswith("job-") for item in outcomes) == 1
    assert outcomes.count("project already has an active preparation chain") == 1


def test_failed_serial_experiment_blocks_and_retry_resumes_later_arms(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="串行失败", user_request="写作", materials=[("", "材料")]
    )
    rule_ids = [
        service.library.add_rule(name=f"规则 {index}", body=f"方法 {index}", activate=index == 1).id
        for index in range(1, 6)
    ]
    service.workflows.create_handoff_revision(
        project_id=project_id,
        core=HandoffCore(user_request="写作", purified_material="材料"),
        case_ids=[],
        hook_ids=[],
    )
    service.handoffs.approve(project_id)
    service.providers.add(
        profile_id="provider-serial-failure",
        name="串行失败配置",
        adapter="openai-responses",
        base_url="https://provider.invalid/v1",
        model="fixed-model",
        capabilities={"web_search": False, "structured_output": True},
        parameters={},
        secret_key_name="unused",
        activate=True,
    )
    experiment_id = service.experiments.start_rule_comparison(
        project_id,
        rule_ids=rule_ids,
        provider_profile_id="provider-serial-failure",
    )
    envelope = service.workflows.lease_next_job(project_id, executor="api")
    assert envelope is not None
    service.workflows.fail_attempt(
        job_id=envelope.job_id,
        attempt_id=envelope.attempt_id,
        lease_token=envelope.lease_token,
        error="provider failed",
    )

    failed_states = [job.status for job in service.workflows.list_jobs(project_id)]
    assert failed_states == [JobStatus.FAILED.value] + [JobStatus.BLOCKED.value] * 4
    assert service.workflows.get_experiment(experiment_id).status == "failed"

    service.jobs.retry(envelope.job_id)
    resumed_states = [job.status for job in service.workflows.list_jobs(project_id)]
    assert resumed_states == [JobStatus.PENDING.value] + [JobStatus.WAITING.value] * 4
    assert service.workflows.get_experiment(experiment_id).status == "running"
