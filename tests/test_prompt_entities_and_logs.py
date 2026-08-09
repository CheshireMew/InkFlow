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
    component = (
        (
            Path(__file__).parents[1]
            / "src"
            / "inkflow"
            / "prompt_files"
            / "components"
            / "general-writing-naturalness.txt"
        )
        .read_text(encoding="utf-8-sig")
        .rstrip()
    )
    assert general.system_prompt.endswith(component)
    assert "同一意思说清一次即可" in general.system_prompt
    assert "不虚构个人体验或假装在场" in general.system_prompt
    assert "# AI 味审查与清理" not in general.system_prompt


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


def test_manual_edit_of_current_file_becomes_a_new_active_revision(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    original = service.prompts.get(stage=PromptStage.PREPARE_MATERIAL)
    original_path = Path(service.prompts.entity_path(original))
    original_bytes = original_path.read_bytes()
    editable_path = Path(service.prompts.editable_file(original) or "")
    payload = json.loads(editable_path.read_text(encoding="utf-8"))
    payload["name"] = "用户手动修改的材料提示词"
    payload["system_prompt"] = "只保留用户要求需要的原始材料。"
    editable_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    revised = service.prompts.get(stage=PromptStage.PREPARE_MATERIAL)
    assert revised.id != original.id
    assert revised.revision > original.revision
    assert revised.origin == "user"
    assert revised.name == "用户手动修改的材料提示词"
    assert revised.system_prompt == "只保留用户要求需要的原始材料。"
    assert original_path.read_bytes() == original_bytes
    canonical = json.loads(editable_path.read_text(encoding="utf-8"))
    assert canonical["id"] == revised.id
    assert canonical["revision"] == revised.revision
    assert canonical["source"]["kind"] == "user-manual-file-edit"


def test_user_prompt_save_creates_new_entity_and_tampering_is_rejected(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    row = service.add_prompt(
        stage=PromptStage.PREPARE_MATERIAL,
        name="用户明确保存的版本",
        system_prompt="只按用户确认的要求准备材料。",
        user_template="要求：{{user_request}}\n材料：{{materials}}",
        activate=True,
    )
    path = (service.prompts.root / row.entity_file).resolve()
    editable_path = Path(service.prompts.editable_file(row) or "")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source"] == {"kind": "user"}
    assert payload["system_prompt"] == "只按用户确认的要求准备材料。"

    before_model_run = path.read_bytes()
    editable_before_model_run = editable_path.read_bytes()
    project_id = service.create_project(
        title="AI 只读提示词", user_request="准备", materials=[("", "原材料")]
    )
    service.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    envelope = service.lease_external_job(project_id)
    assert envelope is not None
    service.submit_job_result(
        envelope.job_id,
        attempt_id=envelope.attempt_id,
        lease_token=envelope.lease_token,
        raw_response=json.dumps(
            {"purified_material": "原材料", "discovered_sources": [], "other_inputs": "无"},
            ensure_ascii=False,
        ),
    )
    assert path.read_bytes() == before_model_run
    assert editable_path.read_bytes() == editable_before_model_run

    payload["system_prompt"] = "未经用户确认的修改"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="differs from immutable database index"):
        service.prompts.get(row.id)


def test_external_ai_boundary_logs_full_request_and_response(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    service = make_service(tmp_path)
    project_id = service.create_project(
        title="完整日志",
        user_request="保留这一条完整要求",
        materials=[("", "保留这一段完整材料")],
    )
    service.start_preparation(project_id, executor=ExecutorKind.EXTERNAL)
    envelope = service.lease_external_job(project_id)
    assert envelope is not None
    request_log = capfd.readouterr().err
    snapshot = envelope.payload["prompt_snapshot"]
    assert snapshot["system_prompt"] in request_log
    assert snapshot["user_prompt"] in request_log
    assert "AI REQUEST BEGIN" in request_log and "AI REQUEST END" in request_log

    raw_response = json.dumps(
        {
            "purified_material": "完整净化材料",
            "discovered_sources": [],
            "other_inputs": "无",
        },
        ensure_ascii=False,
    )
    service.submit_job_result(
        envelope.job_id,
        attempt_id=envelope.attempt_id,
        lease_token=envelope.lease_token,
        raw_response=raw_response,
    )
    response_log = capfd.readouterr().err
    assert raw_response in response_log
    assert "AI RESPONSE BEGIN" in response_log and "AI RESPONSE END" in response_log
