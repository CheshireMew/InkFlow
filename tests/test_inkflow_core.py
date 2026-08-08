from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from inkflow.boundaries import sanitize_handoff_material
from inkflow.domain import ExecutorKind, ExperimentStatus, JobKind, JobStatus, ReferenceKind
from inkflow.providers.base import ProviderCapabilities, ProviderResponse
from inkflow.service import InkFlowService
from inkflow.storage import Database


def make_service(tmp_path: Path) -> InkFlowService:
    return InkFlowService(Database(tmp_path / "inkflow.sqlite3"))


def seed_references_and_rules(service: InkFlowService) -> tuple[str, str, list[str]]:
    case = service.repository.add_reference(
        reference_id="case-direct-change",
        kind=ReferenceKind.CASE,
        title="政策变化短帖",
        body="平台政策彻底改了！\n\n先说变化，再给最直接的影响。",
        formats=["short"],
        techniques=["直接宣布变化", "信息递进"],
    )
    hook = service.repository.add_reference(
        reference_id="hook-direct-change",
        kind=ReferenceKind.HOOK,
        title="变化宣告",
        body="X 的创作者分成政策，彻底改了！",
        formats=["short"],
        techniques=["直接宣布变化"],
    )
    rules = [
        service.add_rule(
            name="短内容规则",
            body=f"规则版本 {index}：每句话都提供新的事实或有效表达。",
            activate=index == 1,
        ).id
        for index in range(1, 6)
    ]
    return case.id, hook.id, rules


def prepare_approved_handoff(service: InkFlowService, case_id: str, hook_id: str) -> str:
    project_id = service.create_project(
        title="X 原创内容奖励计划",
        user_request="根据材料写一篇有吸引力、没有 AI 味的中文短内容。",
        materials=[
            (
                "C:\\Users\\Someone\\attachments\\policy.txt",
                "X 从 8 月 7 日停止旧计划新申请。9 月 8 日开放原创内容奖励计划。",
            )
        ],
    )
    service.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    prepare_job = service.lease_external_job(project_id)
    assert prepare_job is not None and prepare_job.kind is JobKind.PREPARE_MATERIAL
    service.submit_job(
        prepare_job.job_id,
        lease_token=prepare_job.lease_token,
        result={
            "purified_material": (
                "来源：https://example.com/policy\n"
                "C:\\Users\\Someone\\attachments\\policy.txt\n"
                "X 从 8 月 7 日停止旧计划新申请。详情见 https://example.com/detail\n\n"
                "9 月 8 日开放原创内容奖励计划。"
            ),
            "discovered_sources": [
                {
                    "content": "补充：批量自动化生成或发布的内容不合格。",
                    "url": "https://example.com/new",
                }
            ],
            "other_inputs": "无",
        },
    )

    selection_job = service.lease_external_job(project_id)
    assert selection_job is not None and selection_job.kind is JobKind.SELECT_REFERENCES
    service.submit_job(
        selection_job.job_id,
        lease_token=selection_job.lease_token,
        result={"case_ids": [case_id], "hook_ids": [hook_id]},
    )
    handoff = service.repository.get_handoff(project_id)
    core = service.repository.handoff_core(handoff)
    assert "example.com" not in core.purified_material
    assert "attachments" not in core.purified_material
    assert core.reference_cases == ["平台政策彻底改了！\n\n先说变化，再给最直接的影响。"]
    assert core.reference_hooks == ["X 的创作者分成政策，彻底改了！"]
    assert "原文全文" not in service.render_handoff(project_id)
    assert "钩子原文" not in service.render_handoff(project_id)
    service.approve_handoff(project_id)
    return project_id


def test_material_sanitizer_removes_provenance_and_links() -> None:
    text = (
        "材料文件：政策.txt\n"
        "C:\\Users\\Someone\\AppData\\Local\\Temp\\policy.txt\n"
        "[官方说明](https://example.com/a) 里写明了变化。\n"
        "另一条 https://example.com/b，链接不进入交接。"
    )
    assert sanitize_handoff_material(text) == "官方说明 里写明了变化。\n另一条，链接不进入交接。"


def test_batch_five_and_serial_rule_comparison_use_approved_handoff(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    case_id, hook_id, rule_ids = seed_references_and_rules(service)
    project_id = prepare_approved_handoff(service, case_id, hook_id)

    batch_id = service.start_generation(
        project_id,
        executor=ExecutorKind.EXTERNAL,
        batch_five=True,
    )
    batch_job = service.lease_external_job(project_id)
    assert batch_job is not None and batch_job.kind is JobKind.GENERATE
    assert batch_job.payload["output_count"] == 5
    outputs = [f"第 {index} 篇原始成品" for index in range(1, 6)]
    service.submit_job(
        batch_job.job_id,
        lease_token=batch_job.lease_token,
        result={"outputs": outputs},
    )
    assert service.repository.get_experiment(batch_id).status == ExperimentStatus.COMPLETED.value
    assert [row.content for row in service.repository.list_generations(project_id)] == outputs

    comparison_id = service.start_rule_comparison(
        project_id,
        executor=ExecutorKind.EXTERNAL,
        rule_ids=rule_ids,
    )
    packages: list[str] = []
    for index in range(5):
        envelope = service.lease_external_job(project_id)
        assert envelope is not None
        assert envelope.payload["output_count"] == 1
        packages.append(envelope.payload["model_input"])
        pending_generation_jobs = [
            row
            for row in service.repository.list_jobs(project_id)
            if row.experiment_id == comparison_id
            and row.status in {JobStatus.PENDING.value, JobStatus.LEASED.value}
        ]
        assert len(pending_generation_jobs) == 1
        service.submit_job(
            envelope.job_id,
            lease_token=envelope.lease_token,
            result={"outputs": [f"规则 {index + 1} 的原始成品"]},
        )

    assert (
        service.repository.get_experiment(comparison_id).status == ExperimentStatus.COMPLETED.value
    )
    fixed_packages = [
        package.replace(f"规则版本 {index}：每句话都提供新的事实或有效表达。", "<WRITING_RULE>")
        for index, package in enumerate(packages, start=1)
    ]
    assert len(set(fixed_packages)) == 1
    assert all("C:\\Users" not in package and "example.com" not in package for package in packages)
    assert len(service.repository.list_generations(project_id)) == 10


def test_invalid_generation_does_not_complete_job(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    case_id, hook_id, _ = seed_references_and_rules(service)
    project_id = prepare_approved_handoff(service, case_id, hook_id)
    service.start_generation(project_id, executor=ExecutorKind.EXTERNAL, batch_five=True)
    envelope = service.lease_external_job(project_id)
    assert envelope is not None
    with pytest.raises(ValueError, match="expected 5"):
        service.submit_job(
            envelope.job_id,
            lease_token=envelope.lease_token,
            result={"outputs": ["只有一篇"]},
        )
    assert service.repository.get_job(envelope.job_id).status == JobStatus.LEASED.value
    assert service.repository.list_generations(project_id) == []


def test_reference_selection_rejects_wrong_kind_before_completing(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    case_id, hook_id, _ = seed_references_and_rules(service)
    project_id = service.create_project(
        title="测试", user_request="写短内容", materials=[("", "材料")]
    )
    service.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    prepare = service.lease_external_job(project_id)
    assert prepare is not None
    service.submit_job(
        prepare.job_id,
        lease_token=prepare.lease_token,
        result={"purified_material": "材料", "discovered_sources": [], "other_inputs": "无"},
    )
    selection = service.lease_external_job(project_id)
    assert selection is not None
    with pytest.raises(ValueError, match="case_ids"):
        service.submit_job(
            selection.job_id,
            lease_token=selection.lease_token,
            result={"case_ids": [hook_id], "hook_ids": [case_id]},
        )
    assert service.repository.get_job(selection.job_id).status == JobStatus.LEASED.value


def test_job_payload_is_real_producer_output_not_consumer_fixture(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    case_id, hook_id, _ = seed_references_and_rules(service)
    project_id = prepare_approved_handoff(service, case_id, hook_id)
    service.start_generation(project_id, executor=ExecutorKind.EXTERNAL)
    envelope = service.lease_external_job(project_id)
    assert envelope is not None
    handoff = service.repository.get_handoff(project_id, approved=True)
    assert envelope.payload["handoff_core_hash"] == handoff.core_hash
    assert envelope.input_hash == service.repository.get_job(envelope.job_id).input_hash
    assert json.loads(service.repository.get_job(envelope.job_id).payload_json) == envelope.payload
    assert envelope.payload["instruction"]


def test_api_executor_consumes_the_same_job_instruction(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    case_id, hook_id, _ = seed_references_and_rules(service)
    service.repository.save_provider_profile(
        name="fake",
        adapter="openai-responses",
        base_url="https://provider.invalid/v1",
        model="fake-model",
        capabilities={"web_search": True},
        parameters={},
        secret_key_name="unused",
        activate=True,
    )

    calls: list[tuple[str, bool]] = []

    class FakeProvider:
        capabilities = ProviderCapabilities(web_search=True)

        async def complete(self, *, system: str, user: str, use_web_search: bool = False):
            calls.append((system, use_web_search))
            if "正式交接材料" in system:
                content = json.dumps(
                    {
                        "purified_material": "X 正在更换创作者奖励计划。",
                        "discovered_sources": [],
                        "other_inputs": "无",
                    },
                    ensure_ascii=False,
                )
            elif "选择有帮助的参考写作案例" in system:
                content = json.dumps(
                    {"case_ids": [case_id], "hook_ids": [hook_id]},
                    ensure_ascii=False,
                )
            else:
                content = json.dumps({"outputs": ["API 原始成品"]}, ensure_ascii=False)
            return ProviderResponse(
                content=content,
                raw={},
                provider="fake",
                model="fake-model",
            )

    monkeypatch.setattr("inkflow.service.create_provider", lambda _profile: FakeProvider())
    project_id = service.create_project(
        title="API 链路",
        user_request="写短内容",
        materials=[("", "X 正在更换创作者奖励计划。")],
    )
    service.start_preparation(project_id, executor=ExecutorKind.API)
    asyncio.run(service.run_api_jobs(project_id))
    service.approve_handoff(project_id)
    service.start_generation(project_id, executor=ExecutorKind.API)
    asyncio.run(service.run_api_jobs(project_id))

    assert [row.content for row in service.repository.list_generations(project_id)] == [
        "API 原始成品"
    ]
    assert calls[0][1] is True
    assert calls[1][1] is False
    assert calls[2][1] is False
    assert "只生成一篇完整成品" in calls[2][0]
