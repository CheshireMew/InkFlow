from __future__ import annotations

from inkflow.application.provider_runtime import ProviderRuntime
from inkflow.domain import (
    ExecutionPackage,
    ExecutorKind,
    ExperimentKind,
    ExternalGenerationResult,
    GenerationResult,
    PromptStage,
    stable_hash,
)
from inkflow.prompting import render_prompt
from inkflow.storage import LibraryStore, PromptStore, WorkflowStore
from inkflow.storage.schema import WritingRuleRow
from inkflow.storage.workflows import ExperimentJobSpec


class Experiments:
    def __init__(
        self,
        *,
        library: LibraryStore,
        prompts: PromptStore,
        workflows: WorkflowStore,
        provider_runtime: ProviderRuntime,
    ) -> None:
        self.library = library
        self.prompts = prompts
        self.workflows = workflows
        self.provider_runtime = provider_runtime

    def start_generation(
        self,
        project_id: str,
        *,
        executor: ExecutorKind,
        rule_id: str | None = None,
        batch_five: bool = False,
        provider_profile_id: str | None = None,
    ) -> str:
        self.provider_runtime.validate_executor(executor, provider_profile_id)
        rule = self.library.get_rule(rule_id)
        kind = ExperimentKind.BATCH_FIVE if batch_five else ExperimentKind.SINGLE
        return self._start(
            project_id,
            kind=kind,
            executor=executor,
            rules=[rule],
            provider_profile_id=provider_profile_id,
        )

    def start_rule_comparison(
        self,
        project_id: str,
        *,
        rule_ids: list[str],
        provider_profile_id: str,
    ) -> str:
        self.provider_runtime.validate_executor(ExecutorKind.API, provider_profile_id)
        if len(rule_ids) != 5:
            raise ValueError("compare-rules requires exactly five rule revisions")
        rules = [self.library.get_rule(rule_id) for rule_id in rule_ids]
        if len({rule.body_hash for rule in rules}) != 5:
            raise ValueError("compare-rules requires five different rule bodies")
        return self._start(
            project_id,
            kind=ExperimentKind.COMPARE_RULES,
            executor=ExecutorKind.API,
            rules=rules,
            provider_profile_id=provider_profile_id,
        )

    def _start(
        self,
        project_id: str,
        *,
        kind: ExperimentKind,
        executor: ExecutorKind,
        rules: list[WritingRuleRow],
        provider_profile_id: str | None,
    ) -> str:
        handoff = self.workflows.get_handoff(project_id, approved=True)
        prompt = self.prompts.get(PromptStage.GENERATE)
        definition = self.prompts.definition(prompt)
        provider_snapshot = self.provider_runtime.snapshot(
            executor, provider_profile_id
        )
        output_count = 5 if kind is ExperimentKind.BATCH_FIVE else 1
        settings = {"output_count": output_count}
        input_package_hash = stable_hash(
            {
                "handoff_core_hash": handoff.core_hash,
                "executor": executor.value,
                "provider_config_hash": provider_snapshot.get("config_hash"),
                "prompt_hash": definition.prompt_hash,
                "generation_settings": settings,
            }
        )
        jobs: list[ExperimentJobSpec] = []
        for rule in rules:
            package = ExecutionPackage(
                handoff=self.workflows.handoff_core(handoff), writing_rule=rule.body
            )
            prompt_snapshot = render_prompt(
                definition,
                {"execution_package": package.render()},
                output_count=output_count,
            )
            jobs.append(
                ExperimentJobSpec(
                    rule=rule,
                    payload={
                        "schema_version": 2,
                        "handoff_core_hash": handoff.core_hash,
                        "writing_rule_id": rule.id,
                        "writing_rule_hash": rule.body_hash,
                        "prompt_snapshot": prompt_snapshot.model_dump(mode="json"),
                        "provider_snapshot": provider_snapshot,
                        "generation_settings": settings,
                        "result_schema": (
                            ExternalGenerationResult.model_json_schema()
                            if executor is ExecutorKind.EXTERNAL
                            else GenerationResult.model_json_schema()
                        ),
                    },
                )
            )
        self._validate_shared_inputs(
            jobs,
            executor=executor,
            input_package_hash=input_package_hash,
        )
        experiment = self.workflows.create_experiment(
            project_id=project_id,
            handoff_id=handoff.id,
            kind=kind.value,
            executor=executor.value,
            provider_profile_id=provider_snapshot.get("id"),
            prompt_snapshot={
                "definition": definition.model_dump(mode="json"),
                "system_prompt": jobs[0].payload["prompt_snapshot"]["system_prompt"],
            },
            provider_snapshot=provider_snapshot,
            generation_settings=settings,
            input_package_hash=input_package_hash,
            jobs=jobs,
        )
        return experiment.id

    @staticmethod
    def _validate_shared_inputs(
        jobs: list[ExperimentJobSpec],
        *,
        executor: ExecutorKind,
        input_package_hash: str,
    ) -> None:
        for job in jobs:
            payload = job.payload
            actual = stable_hash(
                {
                    "handoff_core_hash": payload["handoff_core_hash"],
                    "executor": executor.value,
                    "provider_config_hash": payload["provider_snapshot"].get(
                        "config_hash"
                    ),
                    "prompt_hash": payload["prompt_snapshot"]["definition"][
                        "prompt_hash"
                    ],
                    "generation_settings": payload["generation_settings"],
                }
            )
            if actual != input_package_hash:
                raise RuntimeError(
                    "experiment arms do not share the same input package"
                )
