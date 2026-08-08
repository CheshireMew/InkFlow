from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from inkflow.cli import app

REAL_100X_LIBRARY = Path(r"E:\Work\BaiduSyncdisk\Code\100x-learning\System Knowledge")


@pytest.mark.skipif(
    not (REAL_100X_LIBRARY / "Home.md").is_file(), reason="local 100x library is unavailable"
)
def test_cli_drives_the_full_external_writing_chain(tmp_path: Path) -> None:
    runner = CliRunner()
    prefix = ["--data-dir", str(tmp_path / "data")]

    imported = invoke_json(runner, prefix + ["reference", "import-100x", str(REAL_100X_LIBRARY)])
    assert imported["cases_imported"] == 34
    assert imported["hooks_imported"] == 7

    project = invoke_json(
        runner,
        prefix
        + [
            "project",
            "create",
            "--title",
            "X 政策",
            "--request",
            "写成有吸引力、没有 AI 味的中文短内容",
            "--material",
            "X 将旧创作者计划换成原创内容奖励计划。",
        ],
    )
    project_id = project["project_id"]

    invoke_json(runner, prefix + ["prepare", "start", project_id])
    prepare = invoke_json(runner, prefix + ["job", "next", "--project", project_id])
    assert prepare["kind"] == "prepare_material"
    invoke_json(
        runner,
        prefix
        + [
            "job",
            "submit",
            prepare["job_id"],
            "--lease-token",
            prepare["lease_token"],
            "--result",
            json.dumps(
                {
                    "purified_material": "X 将旧创作者计划换成原创内容奖励计划。",
                    "discovered_sources": [],
                    "other_inputs": "无",
                },
                ensure_ascii=False,
            ),
        ],
    )

    selection = invoke_json(runner, prefix + ["job", "next", "--project", project_id])
    assert selection["kind"] == "select_references"
    case_id = selection["payload"]["reference_index"]["cases"][0]["id"]
    hook_id = selection["payload"]["reference_index"]["hooks"][0]["id"]
    invoke_json(
        runner,
        prefix
        + [
            "job",
            "submit",
            selection["job_id"],
            "--lease-token",
            selection["lease_token"],
            "--result",
            json.dumps({"case_ids": [case_id], "hook_ids": [hook_id]}, ensure_ascii=False),
        ],
    )

    handoff = invoke_json(runner, prefix + ["handoff", "show", project_id])
    assert handoff["handoff"]["status"] == "draft"
    assert handoff["core"]["reference_cases"]
    assert handoff["core"]["reference_hooks"]
    invoke_json(runner, prefix + ["handoff", "approve", project_id])

    invoke_json(runner, prefix + ["generate", "start", project_id, "--batch-five"])
    generation = invoke_json(runner, prefix + ["job", "next", "--project", project_id])
    assert generation["payload"]["output_count"] == 5
    outputs = [f"CLI 原始成品 {index}" for index in range(1, 6)]
    invoke_json(
        runner,
        prefix
        + [
            "job",
            "submit",
            generation["job_id"],
            "--lease-token",
            generation["lease_token"],
            "--result",
            json.dumps({"outputs": outputs}, ensure_ascii=False),
        ],
    )
    results = invoke_json(runner, prefix + ["result", "list", project_id])
    assert [item["content"] for item in results] == outputs


def invoke_json(runner: CliRunner, args: list[str]):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)
