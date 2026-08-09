from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from inkflow.api import create_app


def test_api_serves_project_state_from_the_same_core(tmp_path: Path) -> None:
    app = create_app(tmp_path / "data")
    client = TestClient(app)
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert '<div id="root"></div>' in frontend.text

    prompts = client.get("/api/prompts")
    assert prompts.status_code == 200
    active_prompt = next(item for item in prompts.json() if item["active"])
    assert Path(active_prompt["entity_path"]).is_file()
    assert Path(active_prompt["editable_file"]).is_file()

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
        json={"executor": "external", "run": False},
    )
    assert started.status_code == 200
    leased = client.get("/api/jobs/next", params={"project_id": project_id})
    assert leased.status_code == 200
    payload = leased.json()
    assert payload["kind"] == "prepare_material"
    assert payload["payload"]["materials"] == ["只有一份真实材料"]


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
        json={"executor": "external", "run": False},
    ).raise_for_status()
    prepare = client.get("/api/jobs/next", params={"project_id": project_id}).json()
    client.post(
        f"/api/jobs/{prepare['job_id']}/submit",
        json={
            "attempt_id": prepare["attempt_id"],
            "lease_token": prepare["lease_token"],
            "result": {
                "purified_material": "真实材料",
                "discovered_sources": [],
                "other_inputs": "无",
            },
        },
    ).raise_for_status()
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
        json={"executor": "external", "run": False, "rule_id": rule["id"]},
    ).json()["experiment_id"]
    generation = client.get("/api/jobs/next", params={"project_id": project_id}).json()
    client.post(
        f"/api/jobs/{generation['job_id']}/submit",
        json={
            "attempt_id": generation["attempt_id"],
            "lease_token": generation["lease_token"],
            "result": {"outputs": ["模型第一次交付"]},
        },
    ).raise_for_status()

    result = client.get(f"/api/projects/{project_id}/results").json()[0]
    assert result["model_content"] == "模型第一次交付"
    assert result["current_content"] == "模型第一次交付"
    assert result["writing_rule"]["body"] == "直接写。"
    assert result["prompt_snapshot"]["user_prompt"]
    experiment = client.get(f"/api/experiments/{experiment_id}").json()
    assert experiment["experiment"]["status"] == "completed"
    assert experiment["arms"][0]["result"]["id"] == result["id"]

    client.post(
        f"/api/results/{result['id']}/revisions", json={"content": "用户修改后的版本"}
    ).raise_for_status()
    edited = client.get(f"/api/projects/{project_id}/results").json()[0]
    assert edited["model_content"] == "模型第一次交付"
    assert edited["current_content"] == "用户修改后的版本"
    exported = client.get(f"/api/results/{result['id']}/export")
    assert exported.text == "用户修改后的版本\n"
