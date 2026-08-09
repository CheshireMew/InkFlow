from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from inkflow.boundaries import sanitize_handoff_material
from inkflow.domain import (
    ExecutionPackage,
    ExecutorKind,
    ExperimentKind,
    GenerationResult,
    HandoffCore,
    JobEnvelope,
    JobKind,
    PreparationResult,
    PromptDefinition,
    PromptStage,
    ReferenceKind,
    ReferenceSelectionResult,
    stable_hash,
)
from inkflow.prompt_entities import read_operational_prompt
from inkflow.prompting import render_prompt
from inkflow.providers.base import ProviderResponse
from inkflow.providers.factory import create_provider, save_api_key
from inkflow.reference_import import ImportReport, import_100x_library
from inkflow.source_import import extract_url
from inkflow.storage import (
    Database,
    LibraryStore,
    ProjectStore,
    PromptStore,
    ProviderStore,
    ResultStore,
    WorkflowStore,
)
from inkflow.storage.common import loads, new_id
from inkflow.storage.schema import WritingRuleRow
from inkflow.storage.workflows import ExperimentJobSpec
from inkflow.structured_data import StructuredResultError, parse_model_json


class InkFlowService:
    """Application composition root. Business decisions live in their domain stores."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        self.projects = ProjectStore(database)
        self.library = LibraryStore(database)
        self.prompts = PromptStore(database)
        self.providers = ProviderStore(database)
        self.workflows = WorkflowStore(database)
        self.results = ResultStore(database)
        self.prompts.ensure_bundled()

    def import_100x(self, library_root: Path) -> ImportReport:
        return import_100x_library(self.library, library_root)

    def create_project(
        self, *, title: str, user_request: str, materials: list[tuple[str, str]]
    ) -> str:
        project = self.projects.create(title=title, user_request=user_request)
        for source_name, content in materials:
            self.projects.add_source(
                project.id,
                kind="file" if source_name else "pasted",
                content=content,
                provenance={"source_name": source_name} if source_name else {},
            )
        return project.id

    def update_project_request(self, project_id: str, user_request: str) -> None:
        self.projects.update_request(project_id, user_request)

    def add_source(
        self, project_id: str, *, content: str, kind: str, provenance: dict[str, Any]
    ) -> str:
        return self.projects.add_source(
            project_id, kind=kind, content=content, provenance=provenance
        ).id

    def add_url_source(self, project_id: str, url: str) -> str:
        content, provenance = extract_url(url)
        return self.add_source(project_id, content=content, kind="url", provenance=provenance)

    def start_preparation(
        self,
        project_id: str,
        *,
        executor: ExecutorKind,
        prepare_prompt_id: str | None = None,
        reference_prompt_id: str | None = None,
        provider_profile_id: str | None = None,
    ) -> str:
        project = self.projects.get(project_id)
        sources = self.projects.list_sources(project_id)
        if not sources:
            raise ValueError("project has no source material")
        prepare_prompt = self.prompts.get(prepare_prompt_id, stage=PromptStage.PREPARE_MATERIAL)
        reference_prompt = self.prompts.get(
            reference_prompt_id, stage=PromptStage.SELECT_REFERENCES
        )
        materials = [source.content for source in sources]
        prepare_snapshot = render_prompt(
            self.prompts.definition(prepare_prompt),
            {
                "user_request": project.user_request,
                "materials": "\n\n".join(materials),
            },
        )
        provider_snapshot = self._provider_snapshot(executor, provider_profile_id)
        payload = {
            "schema_version": 2,
            "prompt_snapshot": prepare_snapshot.model_dump(mode="json"),
            "next_prompt_definition": self.prompts.definition(reference_prompt).model_dump(
                mode="json"
            ),
            "provider_snapshot": provider_snapshot,
            "user_request": project.user_request,
            "materials": materials,
            "search_enabled": bool(
                provider_snapshot.get("capabilities", {}).get("web_search")
                if provider_snapshot
                else executor is ExecutorKind.EXTERNAL
            ),
            "result_schema": PreparationResult.model_json_schema(),
        }
        job = self.workflows.create_job(
            project_id=project_id,
            kind=JobKind.PREPARE_MATERIAL,
            executor=executor.value,
            payload=payload,
        )
        return job.id

    async def run_api_jobs(self, project_id: str) -> None:
        while True:
            envelope = self.workflows.lease_next_job(project_id, executor=ExecutorKind.API.value)
            if envelope is None:
                return
            try:
                response = await self._execute_api_job(envelope)
                self.submit_job_result(
                    envelope.job_id,
                    attempt_id=envelope.attempt_id,
                    lease_token=envelope.lease_token,
                    raw_response=response.content,
                    executor_metadata={
                        "provider": response.provider,
                        "model": response.model,
                        "usage": response.usage,
                    },
                    _response_logged=True,
                )
            except StructuredResultError:
                raise
            except Exception as exc:
                self.workflows.fail_attempt(
                    job_id=envelope.job_id,
                    attempt_id=envelope.attempt_id,
                    lease_token=envelope.lease_token,
                    error=str(exc),
                )
                raise

    def lease_external_job(self, project_id: str | None = None) -> JobEnvelope | None:
        envelope = self.workflows.lease_next_job(
            project_id, executor=ExecutorKind.EXTERNAL.value
        )
        if envelope is not None:
            snapshot = envelope.payload["prompt_snapshot"]
            _log_ai_request(
                f"external-job:{envelope.job_id}:attempt:{envelope.attempt_id}",
                str(snapshot["system_prompt"]),
                str(snapshot["user_prompt"]),
            )
        return envelope

    def submit_job_result(
        self,
        job_id: str,
        *,
        attempt_id: str,
        lease_token: str,
        raw_response: str,
        executor_metadata: dict[str, Any] | None = None,
        _response_logged: bool = False,
    ) -> None:
        if not _response_logged:
            _log_ai_response(f"job:{job_id}:attempt:{attempt_id}", raw_response)
        job = self.workflows.get_job(job_id)
        kind = JobKind(job.kind)
        try:
            if kind is JobKind.PREPARE_MATERIAL:
                parsed: BaseModel = parse_model_json(raw_response, PreparationResult)
                if not sanitize_handoff_material(parsed.purified_material):
                    raise ValueError("preparation returned empty purified material")
            elif kind is JobKind.SELECT_REFERENCES:
                parsed = parse_model_json(raw_response, ReferenceSelectionResult)
                self._validate_reference_selection(parsed)
            else:
                parsed = parse_model_json(raw_response, GenerationResult)
                self._validate_generation_result(job.payload_json, parsed)
        except (StructuredResultError, FileNotFoundError, ValueError) as exc:
            failure = (
                exc
                if isinstance(exc, StructuredResultError)
                else StructuredResultError(str(exc), raw_response=raw_response)
            )
            self.workflows.fail_attempt(
                job_id=job_id,
                attempt_id=attempt_id,
                lease_token=lease_token,
                error="submitted result did not satisfy the job contract",
                raw_response=raw_response,
                format_error=str(failure),
            )
            if isinstance(exc, StructuredResultError):
                raise
            raise failure from exc

        if kind is JobKind.PREPARE_MATERIAL:
            assert isinstance(parsed, PreparationResult)
            sanitized = sanitize_handoff_material(parsed.purified_material)
            normalized = parsed.model_dump()
            normalized["purified_material"] = sanitized
            next_payload = self._reference_selection_payload(job.payload_json, normalized)
            self.workflows.complete_preparation(
                job_id=job_id,
                attempt_id=attempt_id,
                lease_token=lease_token,
                result=normalized,
                raw_response=raw_response,
                next_payload=next_payload,
            )
            return
        if kind is JobKind.SELECT_REFERENCES:
            assert isinstance(parsed, ReferenceSelectionResult)
            self.workflows.complete_selection(
                job_id=job_id,
                attempt_id=attempt_id,
                lease_token=lease_token,
                result=parsed.model_dump(),
                raw_response=raw_response,
            )
            return

        assert isinstance(parsed, GenerationResult)
        self.workflows.complete_generation(
            job_id=job_id,
            attempt_id=attempt_id,
            lease_token=lease_token,
            outputs=parsed.outputs,
            raw_response=raw_response,
            executor_metadata=executor_metadata or parsed.executor_metadata,
        )

    def retry_job(self, job_id: str) -> None:
        self.workflows.retry_job(job_id)

    def approve_handoff(self, project_id: str):
        return self.workflows.approve_handoff(project_id)

    def render_handoff(self, project_id: str, *, rule_id: str | None = None) -> str:
        row = self.workflows.get_handoff(project_id)
        core = self.workflows.handoff_core(row)
        rule = self.library.get_rule(rule_id)
        return ExecutionPackage(handoff=core, writing_rule=rule.body).render()

    def revise_handoff(self, project_id: str, core: HandoffCore):
        project = self.projects.get(project_id)
        if core.user_request != project.user_request:
            raise ValueError(
                "user request can only be changed through the project request boundary"
            )
        latest = self.workflows.get_handoff(project_id)
        sanitized = sanitize_handoff_material(core.purified_material)
        if not sanitized:
            raise ValueError("purified material cannot be empty")
        revised = core.model_copy(update={"purified_material": sanitized})
        return self.workflows.create_handoff_revision(
            project_id=project_id,
            core=revised,
            case_ids=loads(latest.reference_case_ids_json, []),
            hook_ids=loads(latest.reference_hook_ids_json, []),
        )

    def add_rule(self, *, name: str, body: str, activate: bool = False):
        return self.library.add_rule(name=name, body=body, activate=activate)

    def activate_rule(self, rule_id: str):
        return self.library.activate_rule(rule_id)

    def add_prompt(
        self,
        *,
        stage: PromptStage,
        name: str,
        system_prompt: str,
        user_template: str,
        activate: bool,
    ):
        return self.prompts.add(
            stage=stage,
            name=name,
            system_prompt=system_prompt,
            user_template=user_template,
            activate=activate,
        )

    def configure_provider(
        self,
        *,
        name: str,
        adapter: str,
        base_url: str,
        model: str,
        api_key: str,
        parameters: dict[str, Any],
        activate: bool,
    ) -> str:
        if adapter not in {"openai-compatible-chat", "openai-responses"}:
            raise ValueError(f"unsupported provider adapter: {adapter}")
        profile_id = new_id("provider")
        secret_key_name = f"provider:{profile_id}"
        save_api_key(secret_key_name, api_key)
        capabilities = {
            "web_search": adapter == "openai-responses",
            "structured_output": False,
        }
        row = self.providers.add(
            profile_id=profile_id,
            name=name,
            adapter=adapter,
            base_url=base_url,
            model=model,
            capabilities=capabilities,
            parameters=parameters,
            secret_key_name=secret_key_name,
            activate=activate,
        )
        return row.id

    async def test_provider(self, profile_id: str | None = None) -> dict[str, Any]:
        profile = self.providers.get(profile_id)
        provider = create_provider(profile)
        prompt = read_operational_prompt("provider-test.prompt.json")
        response = await self._complete_ai(
            provider,
            interaction=f"provider-test:{profile.id}",
            system=prompt.system_prompt,
            user=prompt.user_prompt,
            use_web_search=False,
        )
        parsed = parse_model_json(response.content, _ProviderTestResult)
        return {
            "ok": parsed.ok,
            "provider_profile_id": profile.id,
            "provider": response.provider,
            "model": response.model,
            "usage": response.usage,
        }

    def start_generation(
        self,
        project_id: str,
        *,
        executor: ExecutorKind,
        rule_id: str | None = None,
        batch_five: bool = False,
        provider_profile_id: str | None = None,
        prompt_revision_id: str | None = None,
    ) -> str:
        rule = self.library.get_rule(rule_id)
        kind = ExperimentKind.BATCH_FIVE if batch_five else ExperimentKind.SINGLE
        return self._start_experiment(
            project_id,
            kind=kind,
            executor=executor,
            rules=[rule],
            provider_profile_id=provider_profile_id,
            prompt_revision_id=prompt_revision_id,
        )

    def start_rule_comparison(
        self,
        project_id: str,
        *,
        executor: ExecutorKind,
        rule_ids: list[str],
        provider_profile_id: str | None = None,
        prompt_revision_id: str | None = None,
    ) -> str:
        if len(rule_ids) != 5:
            raise ValueError("compare-rules requires exactly five rule revisions")
        rules = [self.library.get_rule(rule_id) for rule_id in rule_ids]
        if len({rule.body_hash for rule in rules}) != 5:
            raise ValueError("compare-rules requires five different rule bodies")
        return self._start_experiment(
            project_id,
            kind=ExperimentKind.COMPARE_RULES,
            executor=executor,
            rules=rules,
            provider_profile_id=provider_profile_id,
            prompt_revision_id=prompt_revision_id,
        )

    def list_results(self, project_id: str) -> list[dict[str, Any]]:
        views: list[dict[str, Any]] = []
        for row in self.results.list(project_id):
            revisions = self.results.list_revisions(row.id)
            rule = self.library.get_rule(row.writing_rule_id)
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
                    "current_content": revisions[-1].content if revisions else row.content,
                    "edit_revision": revisions[-1].revision if revisions else 0,
                    "selected": row.selected,
                    "executor_metadata": loads(row.executor_metadata_json, {}),
                    "prompt_snapshot": loads(row.prompt_snapshot_json, {}),
                    "provider_snapshot": loads(row.provider_snapshot_json, {}),
                    "generation_settings": loads(row.generation_settings_json, {}),
                    "created_at": row.created_at,
                }
            )
        return views

    def experiment_detail(self, experiment_id: str) -> dict[str, Any]:
        experiment = self.workflows.get_experiment(experiment_id)
        arms = self.workflows.list_experiment_arms(experiment_id)
        results = [
            item
            for item in self.list_results(experiment.project_id)
            if item["experiment_id"] == experiment_id
        ]
        by_rule = {item["writing_rule_id"]: item for item in results}
        return {
            "experiment": {
                "id": experiment.id,
                "project_id": experiment.project_id,
                "handoff_id": experiment.handoff_id,
                "kind": experiment.kind,
                "executor": experiment.executor,
                "fixed_input_hash": experiment.fixed_input_hash,
                "status": experiment.status,
                "prompt_snapshot": loads(experiment.prompt_snapshot_json, {}),
                "provider_snapshot": loads(experiment.provider_snapshot_json, {}),
                "generation_settings": loads(experiment.generation_settings_json, {}),
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
                    "result": by_rule.get(arm.writing_rule_id),
                }
                for arm in arms
            ],
        }

    def doctor(self) -> dict[str, Any]:
        diagnostics = self.database.diagnostics()
        diagnostics.update(
            {
                "ok": True,
                "projects": len(self.projects.list()),
                "references": len(self.library.list_references(include_inactive=True)),
                "rules": len(self.library.list_rules()),
                "prompt_revisions": len(self.prompts.list()),
                "provider_profiles": len(self.providers.list()),
            }
        )
        return diagnostics

    async def _execute_api_job(self, envelope: JobEnvelope) -> ProviderResponse:
        prompt_snapshot = envelope.payload["prompt_snapshot"]
        provider_snapshot = envelope.payload.get("provider_snapshot") or {}
        profile = self.providers.get(provider_snapshot.get("id"))
        if profile.config_hash != provider_snapshot.get("config_hash"):
            raise RuntimeError("provider profile snapshot no longer matches its immutable revision")
        provider = create_provider(profile)
        return await self._complete_ai(
            provider,
            interaction=f"job:{envelope.job_id}:attempt:{envelope.attempt_id}",
            system=str(prompt_snapshot["system_prompt"]),
            user=str(prompt_snapshot["user_prompt"]),
            use_web_search=(
                envelope.kind is JobKind.PREPARE_MATERIAL and bool(provider.capabilities.web_search)
            ),
        )

    @staticmethod
    async def _complete_ai(
        provider,
        *,
        interaction: str,
        system: str,
        user: str,
        use_web_search: bool,
    ) -> ProviderResponse:
        _log_ai_request(interaction, system, user)
        response = await provider.complete(
            system=system,
            user=user,
            use_web_search=use_web_search,
        )
        _log_ai_response(interaction, response.content)
        return response

    def _validate_reference_selection(self, result: BaseModel) -> None:
        assert isinstance(result, ReferenceSelectionResult)
        cases = self.library.get_references(result.case_ids)
        hooks = self.library.get_references(result.hook_ids)
        if any(row.kind != ReferenceKind.CASE.value for row in cases):
            raise ValueError("case_ids can only contain case references")
        if any(row.kind != ReferenceKind.HOOK.value for row in hooks):
            raise ValueError("hook_ids can only contain hook references")
        if {row.body_hash for row in cases} & {row.body_hash for row in hooks}:
            raise ValueError("a reference cannot serve as both case and hook")

    @staticmethod
    def _validate_generation_result(payload_json: str, result: BaseModel) -> None:
        assert isinstance(result, GenerationResult)
        payload = loads(payload_json, {})
        expected = int(payload["generation_settings"]["output_count"])
        if len(result.outputs) != expected:
            raise ValueError(
                f"generation returned {len(result.outputs)} outputs; expected {expected}"
            )
        if any(not output.strip() for output in result.outputs):
            raise ValueError("generation outputs cannot contain empty content")

    def _reference_selection_payload(
        self, prepare_payload_json: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        prepare_payload = loads(prepare_payload_json, {})
        definition = PromptDefinition.model_validate(prepare_payload["next_prompt_definition"])
        index = self._reference_index()
        snapshot = render_prompt(
            definition,
            {
                "user_request": prepare_payload["user_request"],
                "purified_material": result["purified_material"],
                "reference_index": index,
            },
        )
        return {
            "schema_version": 2,
            "prompt_snapshot": snapshot.model_dump(mode="json"),
            "provider_snapshot": prepare_payload.get("provider_snapshot") or {},
            "purified_material": result["purified_material"],
            "other_inputs": result.get("other_inputs") or "无",
            "reference_index": index,
            "result_schema": ReferenceSelectionResult.model_json_schema(),
        }

    def _start_experiment(
        self,
        project_id: str,
        *,
        kind: ExperimentKind,
        executor: ExecutorKind,
        rules: list[WritingRuleRow],
        provider_profile_id: str | None,
        prompt_revision_id: str | None,
    ) -> str:
        handoff = self.workflows.get_handoff(project_id, approved=True)
        prompt_row = self.prompts.get(prompt_revision_id, stage=PromptStage.GENERATE)
        definition = self.prompts.definition(prompt_row)
        provider_snapshot = self._provider_snapshot(executor, provider_profile_id)
        output_count = 5 if kind is ExperimentKind.BATCH_FIVE else 1
        settings = {"output_count": output_count}
        fixed_input_hash = stable_hash(
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
                        "result_schema": GenerationResult.model_json_schema(),
                    },
                )
            )
        self._validate_fixed_experiment_inputs(
            jobs,
            executor=executor,
            fixed_input_hash=fixed_input_hash,
        )
        experiment_prompt = {
            "definition": definition.model_dump(mode="json"),
            "system_prompt": jobs[0].payload["prompt_snapshot"]["system_prompt"],
        }
        experiment = self.workflows.create_experiment(
            project_id=project_id,
            handoff_id=handoff.id,
            kind=kind.value,
            executor=executor.value,
            provider_profile_id=provider_snapshot.get("id"),
            prompt_revision_id=prompt_row.id,
            prompt_snapshot=experiment_prompt,
            provider_snapshot=provider_snapshot,
            generation_settings=settings,
            fixed_input_hash=fixed_input_hash,
            jobs=jobs,
        )
        return experiment.id

    @staticmethod
    def _validate_fixed_experiment_inputs(
        jobs: list[ExperimentJobSpec],
        *,
        executor: ExecutorKind,
        fixed_input_hash: str,
    ) -> None:
        for job in jobs:
            payload = job.payload
            actual = stable_hash(
                {
                    "handoff_core_hash": payload["handoff_core_hash"],
                    "executor": executor.value,
                    "provider_config_hash": payload["provider_snapshot"].get("config_hash"),
                    "prompt_hash": payload["prompt_snapshot"]["definition"]["prompt_hash"],
                    "generation_settings": payload["generation_settings"],
                }
            )
            if actual != fixed_input_hash:
                raise RuntimeError(
                    "experiment arms do not share the same handoff, provider, prompt and settings"
                )

    def _provider_snapshot(
        self, executor: ExecutorKind, provider_profile_id: str | None
    ) -> dict[str, Any]:
        if executor is ExecutorKind.EXTERNAL:
            return {}
        return self.providers.snapshot(self.providers.get(provider_profile_id)).model_dump(
            mode="json"
        )

    def _reference_index(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {"cases": [], "hooks": []}
        for row in self.library.list_references():
            entry = {
                "id": row.id,
                "formats": loads(row.formats_json, []),
                "techniques": loads(row.techniques_json, []),
            }
            bucket = "cases" if row.kind == ReferenceKind.CASE.value else "hooks"
            result[bucket].append(entry)
        return result


class _ProviderTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool


def _log_ai_request(interaction: str, system: str, user: str) -> None:
    print(
        f"AI REQUEST BEGIN | {interaction}\n"
        f"----- SYSTEM PROMPT -----\n{system}\n"
        f"----- USER PROMPT -----\n{user}\n"
        f"AI REQUEST END | {interaction}",
        file=sys.stderr,
        flush=True,
    )


def _log_ai_response(interaction: str, response: str) -> None:
    print(
        f"AI RESPONSE BEGIN | {interaction}\n"
        f"----- RAW RESPONSE -----\n{response}\n"
        f"AI RESPONSE END | {interaction}",
        file=sys.stderr,
        flush=True,
    )
