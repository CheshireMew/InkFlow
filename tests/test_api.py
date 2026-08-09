from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from inkflow.api import create_app
from inkflow.domain import HandoffCore
from inkflow.providers.base import ProviderCapabilities, ProviderResponse


def test_api_serves_project_state_from_the_same_core(tmp_path: Path) -> None:
    app = create_app(tmp_path / "data")
    client = TestClient(app)
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert '<div id="root"></div>' in frontend.text

    prompts = client.get("/api/prompts")
    assert prompts.status_code == 200
    assert len(prompts.json()) == 3
    prepare_prompt = next(
        item for item in prompts.json() if item["stage"] == "prepare_material"
    )
    assert Path(prepare_prompt["current_path"]).is_file()
    assert not {"id", "revision", "active", "entity_file"} & prepare_prompt.keys()
    saved_prompt = client.put(
        "/api/prompts/prepare_material",
        json={
            "name": "API 当前材料提示词",
            "system_prompt": "只保留本次写作真正需要的材料。",
            "user_template": "要求：{{user_request}}\n材料：{{materials}}",
        },
    )
    assert saved_prompt.status_code == 200
    assert saved_prompt.json()["origin"] == "user"
    assert len(client.get("/api/prompts?stage=prepare_material").json()) == 1

    created = client.post(
        "/api/projects",
        json={
            "title": "API 项目",
            "user_request": "写一篇短内容",
            "materials": ["只有一份真实材料"],
        },
    )
    assert created.status_code == 200
    project_id = created.json()["project_id"]

    state = client.get(f"/api/projects/{project_id}")
    assert state.status_code == 200
    assert state.json()["project"]["user_request"] == "写一篇短内容"
    assert state.json()["sources"][0]["content"] == "只有一份真实材料"

    started = client.post(
        f"/api/projects/{project_id}/prepare",
        json={"executor": "external"},
    )
    assert started.status_code == 200
    leased = client.get("/api/jobs/next", params={"project_id": project_id})
    assert leased.status_code == 200
    payload = leased.json()
    assert payload["kind"] == "prepare_material"
    assert payload["payload"]["materials"] == ["只有一份真实材料"]
    assert (
        payload["payload"]["prompt_snapshot"]["definition"]["prompt_hash"]
        == saved_prompt.json()["prompt_hash"]
    )
    assert (
        payload["payload"]["prompt_snapshot"]["definition"]["system_prompt"]
        == "只保留本次写作真正需要的材料。"
    )
    rejected_external_comparison = client.post(
        f"/api/projects/{project_id}/compare-rules",
        json={"rule_ids": ["a", "b", "c", "d", "e"], "executor": "external"},
    )
    assert rejected_external_comparison.status_code == 422


def test_removed_run_flag_is_rejected_before_any_durable_operation(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"))
    project_id = client.post(
        "/api/projects",
        json={"title": "接受边界", "user_request": "写作", "materials": ["材料"]},
    ).json()["project_id"]

    rejected = client.post(
        f"/api/projects/{project_id}/prepare",
        json={"executor": "external", "run": True},
    )

    assert rejected.status_code == 422
    state = client.get(f"/api/projects/{project_id}").json()
    assert state["jobs"] == []
    assert state["experiments"] == []


def test_source_edit_updates_the_project_input_boundary(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"))
    project_id = client.post(
        "/api/projects",
        json={"title": "素材修订", "user_request": "写作", "materials": ["旧材料"]},
    ).json()["project_id"]
    before = client.get(f"/api/projects/{project_id}").json()
    source_id = before["sources"][0]["id"]

    updated = client.put(
        f"/api/projects/{project_id}/sources/{source_id}",
        json={"content": "完整的新材料"},
    )

    assert updated.status_code == 200
    after = client.get(f"/api/projects/{project_id}").json()
    assert after["project"]["input_revision"] == before["project"]["input_revision"] + 1
    assert after["sources"][0]["content"] == "完整的新材料"


def test_api_produces_a_result_that_the_workbench_reads_and_exports(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "data"))
    project_id = client.post(
        "/api/projects",
        json={"title": "用户链", "user_request": "写一篇短内容", "materials": ["真实材料"]},
    ).json()["project_id"]
    rule = client.post(
        "/api/rules", json={"name": "短内容规则", "body": "直接写。", "activate": True}
    ).json()

    client.post(
        f"/api/projects/{project_id}/prepare",
        json={"executor": "external"},
    ).raise_for_status()
    prepare = client.get("/api/jobs/next", params={"project_id": project_id}).json()
    client.post(
        f"/api/jobs/{prepare['job_id']}/submit",
        json={
            "attempt_id": prepare["attempt_id"],
            "lease_token": prepare["lease_token"],
            "result": {
                "purified_material": "真实材料",
                "discovered_sources": [
                    {
                        "title": "外部补充来源",
                        "url": "https://example.com/source",
                        "content": "外部来源采用的原文",
                        "use": "补充背景事实",
                    }
                ],
                "other_inputs": "无",
            },
        },
    ).raise_for_status()
    sources = client.get(f"/api/projects/{project_id}").json()["sources"]
    discovered = next(item for item in sources if item["kind"] == "search")
    assert discovered["content"] == "外部来源采用的原文"
    assert discovered["provenance_json"] == {
        "title": "外部补充来源",
        "url": "https://example.com/source",
        "use": "补充背景事实",
    }
    selection = client.get("/api/jobs/next", params={"project_id": project_id}).json()
    client.post(
        f"/api/jobs/{selection['job_id']}/submit",
        json={
            "attempt_id": selection["attempt_id"],
            "lease_token": selection["lease_token"],
            "result": {"case_ids": [], "hook_ids": []},
        },
    ).raise_for_status()
    client.post(f"/api/projects/{project_id}/handoff/approve").raise_for_status()
    experiment_id = client.post(
        f"/api/projects/{project_id}/generate",
        json={"executor": "external", "rule_id": rule["id"]},
    ).json()["experiment_id"]
    generation = client.get("/api/jobs/next", params={"project_id": project_id}).json()
    client.post(
        f"/api/jobs/{generation['job_id']}/submit",
        json={
            "attempt_id": generation["attempt_id"],
            "lease_token": generation["lease_token"],
            "result": {
                "outputs": ["模型第一次交付"],
                "executor_metadata": {
                    "runtime": "pytest-external",
                    "model": "test-model",
                    "context_mode": "fresh",
                    "tools": [],
                },
            },
        },
    ).raise_for_status()

    result = client.get(f"/api/projects/{project_id}/results").json()[0]
    assert result["model_content"] == "模型第一次交付"
    assert result["current_content"] == "模型第一次交付"
    assert result["writing_rule"]["body"] == "直接写。"
    assert result["prompt_snapshot"]["user_prompt"]
    assert result["review_state"] == "unreviewed"
    assert result["controlled"] is False
    assert result["runtime_label"] == "外部执行 · pytest-external · test-model"
    experiment = client.get(f"/api/experiments/{experiment_id}").json()
    assert experiment["experiment"]["status"] == "completed"
    assert experiment["experiment"]["input_package_hash"]
    assert [item["id"] for item in experiment["arms"][0]["results"]] == [result["id"]]

    reviewed = client.put(
        f"/api/results/{result['id']}/review", json={"state": "accepted"}
    )
    reviewed.raise_for_status()
    assert reviewed.json()["review_state"] == "accepted"
    assert client.post(f"/api/results/{result['id']}/select").status_code in {404, 405}

    client.post(
        f"/api/results/{result['id']}/revisions", json={"content": "用户修改后的版本"}
    ).raise_for_status()
    edited = client.get(f"/api/projects/{project_id}/results").json()[0]
    assert edited["model_content"] == "模型第一次交付"
    assert edited["current_content"] == "用户修改后的版本"
    assert edited["review_state"] == "unreviewed"
    exported = client.get(f"/api/results/{result['id']}/export")
    assert exported.text == "用户修改后的版本\n"


def test_rule_comparison_api_runs_five_controlled_arms(
    monkeypatch, tmp_path: Path
) -> None:
    app = create_app(tmp_path / "data")
    service = app.state.service
    project_id = service.project_inputs.create_project(
        title="受控规则对比", user_request="写一篇短内容", materials=[("", "真实材料")]
    )
    rule_ids = [
        service.library.add_rule(
            name=f"规则 {index}", body=f"只使用方法 {index}。", activate=index == 1
        ).id
        for index in range(1, 6)
    ]
    service.workflows.create_handoff_revision(
        project_id=project_id,
        core=HandoffCore(user_request="写一篇短内容", purified_material="真实材料"),
        case_ids=[],
        hook_ids=[],
    )
    service.handoffs.approve(project_id)
    service.providers.add(
        profile_id="provider-controlled",
        name="受控配置",
        adapter="openai-responses",
        base_url="https://provider.invalid/v1",
        model="fixed-model",
        capabilities={"web_search": False},
        parameters={"temperature": 0},
        secret_key_name="unused",
        activate=True,
    )
    calls = 0

    class FakeProvider:
        capabilities = ProviderCapabilities(web_search=False)

        async def complete(self, **_kwargs):
            nonlocal calls
            calls += 1
            return ProviderResponse(
                content=json.dumps({"outputs": [f"受控结果 {calls}"]}, ensure_ascii=False),
                raw={},
                provider="fake",
                model="fixed-model",
            )

    monkeypatch.setattr(
        "inkflow.application.provider_runtime.create_provider",
        lambda _profile: FakeProvider(),
    )
    client = TestClient(app)
    started = client.post(
        f"/api/projects/{project_id}/compare-rules",
        json={
            "rule_ids": rule_ids,
            "provider_profile_id": "provider-controlled",
        },
    )
    started.raise_for_status()
    detail = client.get(f"/api/experiments/{started.json()['experiment_id']}").json()
    assert calls == 5
    assert detail["experiment"]["executor"] == "api"
    assert detail["experiment"]["status"] == "completed"
    assert all(len(arm["results"]) == 1 for arm in detail["arms"])
    assert all(result["controlled"] for arm in detail["arms"] for result in arm["results"])
