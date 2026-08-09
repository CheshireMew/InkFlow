from __future__ import annotations

import ast
from pathlib import Path

from inkflow.service import InkFlowService
from inkflow.storage import Database


def test_composition_root_contains_no_business_use_case_methods(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    tree = ast.parse(
        (repository / "src" / "inkflow" / "service.py").read_text(encoding="utf-8")
    )
    service_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "InkFlowService"
    )
    methods = {
        node.name for node in service_class.body if isinstance(node, ast.FunctionDef)
    }
    assert methods == {"__init__", "doctor"}

    service = InkFlowService(Database(tmp_path / "inkflow.sqlite3"))
    assert service.project_inputs.projects is service.projects
    assert service.jobs.workflows is service.workflows
    assert service.handoffs.workflows is service.workflows
    assert service.experiments.workflows is service.workflows
    assert service.result_queries.results is service.results
    assert service.provider_runtime.providers is service.providers


def test_preparation_creation_has_no_check_then_write_api() -> None:
    from inkflow.storage.workflows import WorkflowStore

    assert not hasattr(WorkflowStore, "has_active_preparation")
    assert not hasattr(WorkflowStore, "create_job")
    assert hasattr(WorkflowStore, "create_preparation_job")
