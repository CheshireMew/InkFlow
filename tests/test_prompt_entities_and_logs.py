from __future__ import annotations

import json
from pathlib import Path

import pytest

from inkflow.domain import ExecutorKind, PromptStage
from inkflow.prompt_entities import bundled_prompt_entities, bundled_specialized_prompts
from inkflow.service import InkFlowService
from inkflow.storage import Database


def make_service(tmp_path: Path) -> InkFlowService:
    return InkFlowService(Database(tmp_path / "inkflow.sqlite3"))


def test_every_bundled_prompt_is_a_physical_entity_with_complete_github_history() -> None:
    bundled = bundled_prompt_entities()
    paths = [path for path, _entity in bundled]
    entities = [entity for _path, entity in bundled]
    assert all(path.is_file() for path in paths)
    assert len([entity for entity in entities if entity.default_active]) == 3
    assert (
        len(
            [
                entity
                for entity in entities
                if entity.source.get("kind")
                in {
                    "100x-git-history",
                    "100x-archived-git-history",
                }
                and "github-project-short-content" in str(entity.source.get("path"))
            ]
        )
        == 16
    )
    assert (
        len(
            [
                entity
                for entity in entities
                if entity.source.get("kind") == "100x-git-history"
                and "github-project-list" in str(entity.source.get("path"))
            ]
        )
        == 11
    )
    current_single = next(
        entity
        for entity in entities
        if entity.source.get("kind") == "100x-working-tree"
        and entity.source.get("path") == "references/github-project-short-content.md"
    )
    current_list = next(
        entity
        for entity in entities
        if entity.source.get("kind") == "100x-working-tree"
        and entity.source.get("path") == "references/github-project-list.md"
    )
    assert "这里是写作规则的唯一真源" in current_single.system_prompt
    assert "项目身份由官方定位与真实能力共同支撑" in current_single.system_prompt
    assert "参考写作案例和参考开头钩子共同帮助表达" in current_list.system_prompt

    general = next(
        entity
        for entity in entities
        if entity.stage == PromptStage.GENERATE and entity.default_active
    )
    assert general.source == {
        "kind": "inkflow-runtime-contract",
        "creative_rule_source": "writing_rules.body",
    }
    assert "【写作规则】是本次唯一创作方法" in general.system_prompt
    assert "writing-handoff.md" not in general.system_prompt
    assert "自然表达原则" not in general.system_prompt
    assert "第一轮" not in general.system_prompt
    sync_path = Path(__file__).parents[1] / "scripts" / "sync_100x_writing_prompts.py"
    sync_script = sync_path.read_text(encoding="utf-8-sig")
    assert "system_prompt=GENERATION_RUNTIME_CONTRACT" in sync_script
    assert '"creative_rule_source": "writing_rules.body"' in sync_script


def test_all_current_and_historical_ai_flavor_prompts_are_physical() -> None:
    prompts = [entity for _path, entity in bundled_specialized_prompts()]
    history = [
        entity
        for entity in prompts
        if entity.source.get("kind") in {"100x-git-history", "100x-archived-git-history"}
    ]
    assert len(prompts) == 63
    assert (
        len(
            [
                entity
                for entity in history
                if entity.source.get("path") == "references/natural-writing.md"
            ]
        )
        == 25
    )
    assert (
        len(
            [
                entity
                for entity in history
                if entity.source.get("path") == "references/content-audit.md"
            ]
        )
        == 8
    )
    assert (
        len(
            [
                entity
                for entity in history
                if entity.source.get("path") == "references/content-writing.md"
            ]
        )
        == 24
    )
    assert (
        len(
            [
                entity
                for entity in history
                if "content-audit.previous.md" in str(entity.source.get("path"))
            ]
        )
        == 1
    )
    assert (
        len(
            [
                entity
                for entity in history
                if "content-writing.previous.md" in str(entity.source.get("path"))
            ]
        )
        == 1
    )
    combined = next(entity for entity in prompts if entity.purpose == "ai_flavor_audit_and_cleanup")
    assert "# 内容审查" in combined.system_prompt
    assert "# AI 味审查与清理" in combined.system_prompt
    assert "{{draft}}" in combined.user_template


def test_manual_edit_overwrites_the_single_current_prompt(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    original = service.prompts.get(PromptStage.PREPARE_MATERIAL)
    current_path = Path(original.current_path)
    payload = json.loads(current_path.read_text(encoding="utf-8"))
    payload["name"] = "用户手动修改的材料提示词"
    payload["system_prompt"] = "只保留用户要求需要的原始材料。"
    current_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    revised = service.prompts.get(PromptStage.PREPARE_MATERIAL)
    assert revised.prompt_hash != original.prompt_hash
    assert revised.origin == "user"
    assert revised.name == "用户手动修改的材料提示词"
    assert revised.system_prompt == "只保留用户要求需要的原始材料。"
    assert revised.current_path == original.current_path
    canonical = json.loads(current_path.read_text(encoding="utf-8"))
    assert canonical["schema_version"] == 2
    assert not {"id", "revision", "active", "default_active"} & canonical.keys()
    assert len(service.prompts.list(PromptStage.PREPARE_MATERIAL)) == 1


def test_user_prompt_save_overwrites_current_and_ai_uses_a_read_only_snapshot(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    current = service.prompts.save(
        stage=PromptStage.PREPARE_MATERIAL,
        name="用户当前材料提示词",
        system_prompt="只按用户确认的要求准备材料。",
        user_template="要求：{{user_request}}\n材料：{{materials}}",
    )
    path = Path(current.current_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["system_prompt"] == "只按用户确认的要求准备材料。"

    project_id = service.project_inputs.create_project(
        title="AI 只读提示词", user_request="准备", materials=[("", "原材料")]
    )
    service.jobs.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    envelope = service.jobs.lease_external(project_id)
    assert envelope is not None
    snapshot = envelope.payload["prompt_snapshot"]
    assert snapshot["definition"]["prompt_hash"] == current.prompt_hash
    assert snapshot["definition"]["system_prompt"] == "只按用户确认的要求准备材料。"

    replacement = service.prompts.save(
        stage=PromptStage.PREPARE_MATERIAL,
        name="后来覆盖的当前提示词",
        system_prompt="后来只保留必要事实。",
        user_template="要求：{{user_request}}\n材料：{{materials}}",
    )
    before_model_run = path.read_bytes()
    assert replacement.prompt_hash != current.prompt_hash
    service.jobs.submit_result(
        envelope.job_id,
        attempt_id=envelope.attempt_id,
        lease_token=envelope.lease_token,
        raw_response=json.dumps(
            {"purified_material": "原材料", "discovered_sources": [], "other_inputs": "无"},
            ensure_ascii=False,
        ),
    )
    assert path.read_bytes() == before_model_run
    assert envelope.payload["prompt_snapshot"] == snapshot


def test_external_ai_boundary_logs_full_request_and_response(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    service = make_service(tmp_path)
    project_id = service.project_inputs.create_project(
        title="完整日志",
        user_request="保留这一条完整要求",
        materials=[("", "保留这一段完整材料")],
    )
    service.jobs.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    envelope = service.jobs.lease_external(project_id)
    assert envelope is not None
    request_log = capfd.readouterr().err
    snapshot = envelope.payload["prompt_snapshot"]
    request_event = json.loads(request_log)
    assert request_event["event"] == "request"
    assert request_event["component"] == "inkflow.ai"
    assert request_event["system_prompt"] == snapshot["system_prompt"]
    assert request_event["user_prompt"] == snapshot["user_prompt"]
    assert request_event["response_schema"] == envelope.payload["result_schema"]

    raw_response = json.dumps(
        {
            "purified_material": "完整净化材料",
            "discovered_sources": [],
            "other_inputs": "无",
        },
        ensure_ascii=False,
    )
    service.jobs.submit_result(
        envelope.job_id,
        attempt_id=envelope.attempt_id,
        lease_token=envelope.lease_token,
        raw_response=raw_response,
    )
    response_log = capfd.readouterr().err
    response_event = json.loads(response_log)
    assert response_event["event"] == "response"
    assert response_event["result"] == "submitted"
    assert response_event["raw_response"] == raw_response
    persisted = [
        json.loads(line)
        for line in (tmp_path / "logs" / "ai-interactions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [event["event"] for event in persisted] == ["request", "response"]
