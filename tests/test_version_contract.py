from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from inkflow.__about__ import __version__
from inkflow.api import create_app


def test_python_api_frontend_and_diagnostics_share_one_version(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    package = json.loads((repository / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads(
        (repository / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )
    client = TestClient(create_app(tmp_path / "data"))

    assert package["version"] == __version__
    assert lock["version"] == __version__
    assert lock["packages"][""]["version"] == __version__
    assert client.get("/openapi.json").json()["info"]["version"] == __version__
    assert client.get("/api/health").json()["version"] == __version__
