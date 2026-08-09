from __future__ import annotations

from typing import Any

from inkflow.domain import ExecutorKind, ExperimentKind, stable_hash
from inkflow.storage import ResultStore, WorkflowStore
from inkflow.storage.common import loads


class ResultQueries:
    def __init__(self, results: ResultStore, workflows: WorkflowStore) -> None:
        self.results = results
        self.workflows = workflows

    def list(
        self, project_id: str, *, experiment_id: str | None = None
    ) -> list[dict[str, Any]]:
        views: list[dict[str, Any]] = []
        for context in self.results.list_with_context(
            project_id, experiment_id=experiment_id
        ):
            row = context.generation
            revision = context.latest_revision
            rule = context.writing_rule
            experiment = context.experiment
            provider_snapshot = loads(row.provider_snapshot_json, {})
            executor_metadata = loads(row.executor_metadata_json, {})
            api_run = experiment.executor == ExecutorKind.API.value
            controlled = (
                api_run and experiment.kind == ExperimentKind.COMPARE_RULES.value
            )
            runtime_identity = (
                {
                    "executor": experiment.executor,
                    "provider_config_hash": provider_snapshot.get("config_hash"),
                }
                if api_run
                else {
                    "executor": experiment.executor,
                    "declared_runtime": executor_metadata,
                }
            )
            runtime_label = (
                f"内置 API · {provider_snapshot.get('model', '未知模型')}"
                if api_run
                else "外部执行 · "
                + " · ".join(
                    [
                        str(executor_metadata.get("runtime") or "环境未声明"),
                        str(executor_metadata.get("model") or "模型未声明"),
                    ]
                )
            )
            views.append(
                {
                    "id": row.id,
                    "project_id": row.project_id,
                    "job_id": row.job_id,
                    "handoff_id": row.handoff_id,
                    "experiment_id": row.experiment_id,
                    "writing_rule_id": row.writing_rule_id,
                    "writing_rule": {
                        "name": rule.name,
                        "revision": rule.revision,
                        "body": rule.body,
                        "body_hash": rule.body_hash,
                    },
                    "output_index": row.output_index,
                    "model_content": row.content,
                    "current_content": revision.content if revision else row.content,
                    "edit_revision": revision.revision if revision else 0,
                    "review_state": row.review_state,
                    "executor": experiment.executor,
                    "controlled": controlled,
                    "runtime_fingerprint": stable_hash(runtime_identity),
                    "runtime_label": runtime_label,
                    "executor_metadata": executor_metadata,
                    "prompt_snapshot": loads(row.prompt_snapshot_json, {}),
                    "provider_snapshot": provider_snapshot,
                    "generation_settings": loads(row.generation_settings_json, {}),
                    "created_at": row.created_at,
                }
            )
        return views

    def experiment_detail(self, experiment_id: str) -> dict[str, Any]:
        experiment = self.workflows.get_experiment(experiment_id)
        arms = self.workflows.list_experiment_arms(experiment_id)
        results = self.list(experiment.project_id, experiment_id=experiment_id)
        by_rule: dict[str, list[dict[str, Any]]] = {}
        for item in results:
            by_rule.setdefault(item["writing_rule_id"], []).append(item)
        return {
            "experiment": {
                "id": experiment.id,
                "project_id": experiment.project_id,
                "handoff_id": experiment.handoff_id,
                "kind": experiment.kind,
                "executor": experiment.executor,
                "input_package_hash": experiment.input_package_hash,
                "status": experiment.status,
                "prompt_snapshot": loads(experiment.prompt_snapshot_json, {}),
                "provider_snapshot": loads(experiment.provider_snapshot_json, {}),
                "generation_settings": loads(
                    experiment.generation_settings_json, {}
                ),
                "created_at": experiment.created_at,
                "completed_at": experiment.completed_at,
            },
            "arms": [
                {
                    "id": arm.id,
                    "ordinal": arm.ordinal,
                    "status": arm.status,
                    "writing_rule_id": arm.writing_rule_id,
                    "writing_rule_hash": arm.writing_rule_hash,
                    "results": by_rule.get(arm.writing_rule_id, []),
                }
                for arm in arms
            ],
        }
