from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from inkflow.api import create_app


def test_api_serves_project_state_from_the_same_repository(tmp_path: Path) -> None:
    app = create_app(tmp_path / "data")
    client = TestClient(app)
    frontend = client.get("/")
    assert frontend.status_code == 200
    assert '<div id="root"></div>' in frontend.text

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
