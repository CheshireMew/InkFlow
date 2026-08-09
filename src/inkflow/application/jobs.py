from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from inkflow.application.provider_runtime import ProviderRuntime
from inkflow.boundaries import sanitize_handoff_material
from inkflow.domain import (
    ExecutorKind,
    ExternalGenerationResult,
    GenerationResult,
    JobEnvelope,
    JobKind,
    PreparationResult,
    PromptDefinition,
    PromptStage,
    ReferenceKind,
    ReferenceSelectionResult,
)
from inkflow.prompting import render_prompt
from inkflow.runtime_logging import log_ai_event
from inkflow.storage import LibraryStore, ProjectStore, PromptStore, WorkflowStore
from inkflow.storage.common import loads
from inkflow.structured_data import StructuredResultError, parse_model_json


class JobCoordinator:
    def __init__(
        self,
        *,
        projects: ProjectStore,
        library: LibraryStore,
        prompts: PromptStore,
        workflows: WorkflowStore,
        provider_runtime: ProviderRuntime,
    ) -> None:
        self.projects = projects
        self.library = library
        self.prompts = prompts
        self.workflows = workflows
        self.provider_runtime = provider_runtime

    def start_preparation(
        self,
        project_id: str,
        *,
        executor: ExecutorKind,
        provider_profile_id: str | None = None,
    ) -> str:
        self.provider_runtime.validate_executor(executor, provider_profile_id)
        input_snapshot = self.projects.input_snapshot(project_id)
        project = input_snapshot.project
        sources = input_snapshot.sources
        if not sources:
            raise ValueError("project has no source material")
        prepare_prompt = self.prompts.get(PromptStage.PREPARE_MATERIAL)
        reference_prompt = self.prompts.get(PromptStage.SELECT_REFERENCES)
        materials = [source.content for source in sources]
        provider_snapshot = self.provider_runtime.snapshot(executor, provider_profile_id)
        prepare_snapshot = render_prompt(
            self.prompts.definition(prepare_prompt),
            {
                "user_request": project.user_request,
                "materials": "\n\n".join(materials),
            },
        )
        payload = {
            "schema_version": 2,
            "prompt_snapshot": prepare_snapshot.model_dump(mode="json"),
            "next_prompt_definition": self.prompts.definition(
                reference_prompt
            ).model_dump(mode="json"),
            "provider_snapshot": provider_snapshot,
            "project_input": {
                "revision": project.input_revision,
                "user_request": project.user_request,
                "source_hashes": [source.content_hash for source in sources],
            },
            "user_request": project.user_request,
            "materials": materials,
            "search_enabled": bool(
                provider_snapshot.get("capabilities", {}).get("web_search")
                if provider_snapshot
                else executor is ExecutorKind.EXTERNAL
            ),
            "result_schema": PreparationResult.model_json_schema(),
        }
        return self.workflows.create_preparation_job(
            project_id=project_id,
            executor=executor.value,
            payload=payload,
            expected_input_revision=project.input_revision,
        ).id

    async def run_api_jobs(self, project_id: str) -> None:
        while True:
            envelope = self.workflows.lease_next_job(
                project_id, executor=ExecutorKind.API.value
            )
            if envelope is None:
                return
            try:
                response = await self._execute_api_job(envelope)
                self.submit_result(
                    envelope.job_id,
                    attempt_id=envelope.attempt_id,
                    lease_token=envelope.lease_token,
                    raw_response=response.content,
                    executor_metadata={
                        "provider": response.provider,
                        "model": response.model,
                        "usage": response.usage,
                        "request_id": response.request_id,
                        "finish_reason": response.finish_reason,
                    },
                    response_logged=True,
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

    def lease_external(self, project_id: str | None = None) -> JobEnvelope | None:
        envelope = self.workflows.lease_next_job(
            project_id, executor=ExecutorKind.EXTERNAL.value
        )
        if envelope is not None:
            snapshot = envelope.payload["prompt_snapshot"]
            log_ai_event(
                "request",
                f"job:{envelope.job_id}:attempt:{envelope.attempt_id}",
                executor="external",
                job_id=envelope.job_id,
                attempt_id=envelope.attempt_id,
                system_prompt=str(snapshot["system_prompt"]),
                user_prompt=str(snapshot["user_prompt"]),
                response_schema=envelope.payload.get("result_schema"),
            )
        return envelope

    def submit_result(
        self,
        job_id: str,
        *,
        attempt_id: str,
        lease_token: str,
        raw_response: str,
        executor_metadata: dict[str, Any] | None = None,
        response_logged: bool = False,
    ) -> None:
        if not response_logged:
            log_ai_event(
                "response",
                f"job:{job_id}:attempt:{attempt_id}",
                executor="external",
                job_id=job_id,
                attempt_id=attempt_id,
                result="submitted",
                raw_response=raw_response,
            )
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
                generation_contract = (
                    ExternalGenerationResult
                    if job.executor == ExecutorKind.EXTERNAL.value
                    else GenerationResult
                )
                parsed = parse_model_json(raw_response, generation_contract)
                self._validate_generation_result(job.payload_json, parsed)
        except (StructuredResultError, FileNotFoundError, ValueError) as exc:
            failure = (
                exc
                if isinstance(exc, StructuredResultError)
                else StructuredResultError(
                    "contract_violation", str(exc), raw_response=raw_response
                )
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
            normalized = parsed.model_dump()
            normalized["purified_material"] = sanitize_handoff_material(
                parsed.purified_material
            )
            self.workflows.complete_preparation(
                job_id=job_id,
                attempt_id=attempt_id,
                lease_token=lease_token,
                result=normalized,
                raw_response=raw_response,
                next_payload=self._reference_selection_payload(
                    job.payload_json, normalized
                ),
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
        submitted_metadata = (
            parsed.executor_metadata.model_dump(mode="json")
            if isinstance(parsed, ExternalGenerationResult)
            else executor_metadata or {}
        )
        self.workflows.complete_generation(
            job_id=job_id,
            attempt_id=attempt_id,
            lease_token=lease_token,
            outputs=parsed.outputs,
            raw_response=raw_response,
            executor_metadata=submitted_metadata,
        )

    def retry(self, job_id: str):
        return self.workflows.retry_job(job_id)

    async def _execute_api_job(self, envelope: JobEnvelope):
        prompt_snapshot = envelope.payload["prompt_snapshot"]
        return await self.provider_runtime.execute_snapshot(
            provider_snapshot=envelope.payload.get("provider_snapshot") or {},
            interaction=f"job:{envelope.job_id}:attempt:{envelope.attempt_id}",
            system=str(prompt_snapshot["system_prompt"]),
            user=str(prompt_snapshot["user_prompt"]),
            response_schema=envelope.payload["result_schema"],
            use_web_search=(
                envelope.kind is JobKind.PREPARE_MATERIAL
                and bool(
                    (envelope.payload.get("provider_snapshot") or {})
                    .get("capabilities", {})
                    .get("web_search")
                )
            ),
        )

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
        definition = PromptDefinition.model_validate(
            prepare_payload["next_prompt_definition"]
        )
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
            "project_input": prepare_payload["project_input"],
            "purified_material": result["purified_material"],
            "other_inputs": result.get("other_inputs") or "无",
            "reference_index": index,
            "result_schema": ReferenceSelectionResult.model_json_schema(),
        }

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
