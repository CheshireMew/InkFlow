from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from inkflow.domain import ExecutorKind, HandoffCore, PromptStage, ReferenceKind
from inkflow.paths import AppPaths
from inkflow.resources import frontend_dist
from inkflow.serialization import row_dict
from inkflow.service import InkFlowService
from inkflow.storage import Database


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(StrictModel):
    title: str
    user_request: str
    materials: list[str] = Field(default_factory=list)


class ProjectUpdate(StrictModel):
    user_request: str


class SourceCreate(StrictModel):
    content: str | None = None
    url: str | None = None

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.content) == bool(self.url):
            raise ValueError("provide exactly one of content or url")
        return self


class StartPreparation(StrictModel):
    executor: ExecutorKind = ExecutorKind.EXTERNAL
    run: bool = False
    prepare_prompt_id: str | None = None
    reference_prompt_id: str | None = None
    provider_profile_id: str | None = None


class JobSubmission(StrictModel):
    attempt_id: str
    lease_token: str
    result: dict[str, Any]


class RuleCreate(StrictModel):
    name: str
    body: str
    activate: bool = False


class PromptCreate(StrictModel):
    stage: PromptStage
    name: str
    system_prompt: str
    user_template: str
    activate: bool = True


class GenerationStart(StrictModel):
    executor: ExecutorKind = ExecutorKind.EXTERNAL
    run: bool = False
    rule_id: str | None = None
    provider_profile_id: str | None = None
    prompt_revision_id: str | None = None


class ComparisonStart(StrictModel):
    executor: ExecutorKind = ExecutorKind.EXTERNAL
    run: bool = False
    rule_ids: list[str]
    provider_profile_id: str | None = None
    prompt_revision_id: str | None = None


class ProviderConfigure(StrictModel):
    name: str
    adapter: Literal["openai-compatible-chat", "openai-responses"]
    base_url: str
    model: str
    api_key: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    activate: bool = True


class ImportRequest(StrictModel):
    library_root: Path


class ReferenceWrite(StrictModel):
    kind: ReferenceKind
    title: str
    body: str
    formats: list[str] = Field(default_factory=list)
    techniques: list[str] = Field(default_factory=list)
    active: bool = True


class ResultEdit(StrictModel):
    content: str


def create_app(data_dir: Path | None = None) -> FastAPI:
    paths = AppPaths.resolve(override_data_dir=data_dir)
    service = InkFlowService(Database(paths.database_path))
    app = FastAPI(title="InkFlow", version="0.3.0")
    app.state.service = service

    @app.exception_handler(FileNotFoundError)
    async def missing(_request, exc: FileNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(_request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PermissionError)
    async def forbidden(_request, exc: PermissionError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return service.doctor()

    @app.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        return [row_dict(row) for row in service.projects.list()]

    @app.post("/api/projects")
    def create_project(payload: ProjectCreate) -> dict[str, str]:
        project_id = service.create_project(
            title=payload.title,
            user_request=payload.user_request,
            materials=[("", item) for item in payload.materials],
        )
        return {"project_id": project_id}

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        jobs = service.workflows.list_jobs(project_id)
        return {
            "project": row_dict(service.projects.get(project_id)),
            "sources": [row_dict(row) for row in service.projects.list_sources(project_id)],
            "jobs": [
                {
                    **row_dict(row),
                    "attempts": [
                        row_dict(item, omit={"lease_token"})
                        for item in service.workflows.list_attempts(row.id)
                    ],
                }
                for row in jobs
            ],
            "experiments": [
                row_dict(row) for row in service.workflows.list_experiments(project_id)
            ],
        }

    @app.put("/api/projects/{project_id}")
    def update_project(project_id: str, payload: ProjectUpdate) -> dict[str, str]:
        service.update_project_request(project_id, payload.user_request)
        return {"project_id": project_id}

    @app.post("/api/projects/{project_id}/sources")
    def add_source(project_id: str, payload: SourceCreate) -> dict[str, str]:
        if payload.url:
            source_id = service.add_url_source(project_id, payload.url)
        else:
            source_id = service.add_source(
                project_id,
                content=str(payload.content),
                kind="pasted",
                provenance={},
            )
        return {"source_id": source_id}

    @app.post("/api/references/import-100x")
    def import_references(payload: ImportRequest) -> dict[str, object]:
        return service.import_100x(payload.library_root).as_dict()

    @app.get("/api/references")
    def list_references(
        kind: ReferenceKind | None = None, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        return [
            {
                **row_dict(row, omit={"body"}),
                "body_preview": row.body[:180],
            }
            for row in service.library.list_references(kind=kind, include_inactive=include_inactive)
        ]

    @app.get("/api/references/{reference_id}")
    def get_reference(reference_id: str) -> dict[str, Any]:
        return row_dict(service.library.get_reference(reference_id))

    @app.post("/api/references")
    def create_reference(payload: ReferenceWrite) -> dict[str, Any]:
        row = service.library.add_reference(
            reference_id=None,
            kind=payload.kind,
            title=payload.title,
            body=payload.body,
            formats=payload.formats,
            techniques=payload.techniques,
        )
        if not payload.active:
            row = service.library.update_reference(
                row.id,
                title=row.title,
                body=row.body,
                formats=payload.formats,
                techniques=payload.techniques,
                active=False,
            )
        return row_dict(row)

    @app.put("/api/references/{reference_id}")
    def update_reference(reference_id: str, payload: ReferenceWrite) -> dict[str, Any]:
        current = service.library.get_reference(reference_id)
        if current.kind != payload.kind.value:
            raise HTTPException(400, "reference kind is immutable")
        return row_dict(
            service.library.update_reference(
                reference_id,
                title=payload.title,
                body=payload.body,
                formats=payload.formats,
                techniques=payload.techniques,
                active=payload.active,
            )
        )

    @app.post("/api/projects/{project_id}/prepare")
    async def start_preparation(
        project_id: str,
        payload: StartPreparation,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        job_id = service.start_preparation(
            project_id,
            executor=payload.executor,
            prepare_prompt_id=payload.prepare_prompt_id,
            reference_prompt_id=payload.reference_prompt_id,
            provider_profile_id=payload.provider_profile_id,
        )
        if payload.run:
            if payload.executor is not ExecutorKind.API:
                raise HTTPException(400, "run 仅适用于 API 执行器")
            background_tasks.add_task(service.run_api_jobs, project_id)
        return {"job_id": job_id}

    @app.get("/api/jobs/next")
    def next_job(project_id: str | None = None) -> dict[str, Any] | None:
        envelope = service.lease_external_job(project_id)
        return envelope.model_dump(mode="json") if envelope else None

    @app.post("/api/jobs/{job_id}/submit")
    def submit_job(job_id: str, payload: JobSubmission) -> dict[str, str]:
        service.submit_job_result(
            job_id,
            attempt_id=payload.attempt_id,
            lease_token=payload.lease_token,
            raw_response=json.dumps(payload.result, ensure_ascii=False, separators=(",", ":")),
        )
        return {"job_id": job_id, "status": "succeeded"}

    @app.post("/api/jobs/{job_id}/retry")
    def retry_job(job_id: str) -> dict[str, str]:
        service.retry_job(job_id)
        return {"job_id": job_id, "status": "pending"}

    @app.get("/api/projects/{project_id}/handoff")
    def get_handoff(project_id: str) -> dict[str, Any]:
        row = service.workflows.get_handoff(project_id)
        return {
            "handoff": row_dict(row, omit={"reference_cases_json", "reference_hooks_json"}),
            "core": service.workflows.handoff_core(row).model_dump(),
        }

    @app.get("/api/projects/{project_id}/handoffs")
    def handoff_history(project_id: str) -> list[dict[str, Any]]:
        return [
            {
                "handoff": row_dict(row, omit={"reference_cases_json", "reference_hooks_json"}),
                "core": service.workflows.handoff_core(row).model_dump(),
            }
            for row in service.workflows.list_handoffs(project_id)
        ]

    @app.put("/api/projects/{project_id}/handoff")
    def revise_handoff(project_id: str, payload: HandoffCore) -> dict[str, Any]:
        return row_dict(service.revise_handoff(project_id, payload))

    @app.post("/api/projects/{project_id}/handoff/approve")
    def approve_handoff(project_id: str) -> dict[str, Any]:
        return row_dict(service.approve_handoff(project_id))

    @app.get("/api/projects/{project_id}/handoff/render")
    def render_handoff(project_id: str, rule_id: str | None = None) -> dict[str, str]:
        return {"content": service.render_handoff(project_id, rule_id=rule_id)}

    @app.get("/api/rules")
    def list_rules() -> list[dict[str, Any]]:
        return [row_dict(row) for row in service.library.list_rules()]

    @app.post("/api/rules")
    def add_rule(payload: RuleCreate) -> dict[str, Any]:
        return row_dict(
            service.add_rule(name=payload.name, body=payload.body, activate=payload.activate)
        )

    @app.post("/api/rules/{rule_id}/activate")
    def activate_rule(rule_id: str) -> dict[str, Any]:
        return row_dict(service.activate_rule(rule_id))

    @app.get("/api/prompts")
    def list_prompts(stage: PromptStage | None = None) -> list[dict[str, Any]]:
        return [_prompt_view(service, row) for row in service.prompts.list(stage)]

    @app.post("/api/prompts")
    def add_prompt(payload: PromptCreate) -> dict[str, Any]:
        row = service.add_prompt(**payload.model_dump())
        return _prompt_view(service, row)

    @app.post("/api/prompts/{prompt_id}/activate")
    def activate_prompt(prompt_id: str) -> dict[str, Any]:
        row = service.prompts.activate(prompt_id)
        return _prompt_view(service, row)

    @app.post("/api/projects/{project_id}/generate")
    async def start_generation(
        project_id: str,
        payload: GenerationStart,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        experiment_id = service.start_generation(
            project_id,
            executor=payload.executor,
            rule_id=payload.rule_id,
            provider_profile_id=payload.provider_profile_id,
            prompt_revision_id=payload.prompt_revision_id,
        )
        if payload.run:
            if payload.executor is not ExecutorKind.API:
                raise HTTPException(400, "run 仅适用于 API 执行器")
            background_tasks.add_task(service.run_api_jobs, project_id)
        return {"experiment_id": experiment_id}

    @app.post("/api/projects/{project_id}/batch-five")
    async def batch_five(
        project_id: str,
        payload: GenerationStart,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        experiment_id = service.start_generation(
            project_id,
            executor=payload.executor,
            rule_id=payload.rule_id,
            batch_five=True,
            provider_profile_id=payload.provider_profile_id,
            prompt_revision_id=payload.prompt_revision_id,
        )
        if payload.run:
            if payload.executor is not ExecutorKind.API:
                raise HTTPException(400, "run 仅适用于 API 执行器")
            background_tasks.add_task(service.run_api_jobs, project_id)
        return {"experiment_id": experiment_id}

    @app.post("/api/projects/{project_id}/compare-rules")
    async def compare_rules(
        project_id: str,
        payload: ComparisonStart,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        experiment_id = service.start_rule_comparison(
            project_id,
            executor=payload.executor,
            rule_ids=payload.rule_ids,
            provider_profile_id=payload.provider_profile_id,
            prompt_revision_id=payload.prompt_revision_id,
        )
        if payload.run:
            if payload.executor is not ExecutorKind.API:
                raise HTTPException(400, "run 仅适用于 API 执行器")
            background_tasks.add_task(service.run_api_jobs, project_id)
        return {"experiment_id": experiment_id}

    @app.get("/api/experiments/{experiment_id}")
    def experiment_detail(experiment_id: str) -> dict[str, Any]:
        return service.experiment_detail(experiment_id)

    @app.get("/api/projects/{project_id}/results")
    def list_results(project_id: str) -> list[dict[str, Any]]:
        return service.list_results(project_id)

    @app.post("/api/results/{generation_id}/select")
    def select_result(generation_id: str) -> dict[str, Any]:
        service.results.select(generation_id)
        return next(
            item
            for item in service.list_results(service.results.get(generation_id).project_id)
            if item["id"] == generation_id
        )

    @app.post("/api/results/{generation_id}/revisions")
    def edit_result(generation_id: str, payload: ResultEdit) -> dict[str, Any]:
        return row_dict(service.results.add_revision(generation_id, payload.content))

    @app.get("/api/results/{generation_id}/export")
    def export_result(generation_id: str):
        content = service.results.current_content(generation_id)
        return PlainTextResponse(
            content + "\n",
            headers={"Content-Disposition": f'attachment; filename="inkflow-{generation_id}.md"'},
        )

    @app.get("/api/providers")
    def list_providers() -> list[dict[str, Any]]:
        return [row_dict(row, omit={"secret_key_name"}) for row in service.providers.list()]

    @app.post("/api/providers")
    def configure_provider(payload: ProviderConfigure) -> dict[str, str]:
        profile_id = service.configure_provider(**payload.model_dump())
        return {"provider_profile_id": profile_id}

    @app.post("/api/providers/{profile_id}/activate")
    def activate_provider(profile_id: str) -> dict[str, Any]:
        return row_dict(service.providers.activate(profile_id), omit={"secret_key_name"})

    @app.post("/api/providers/{profile_id}/test")
    async def test_provider(profile_id: str) -> dict[str, Any]:
        return await service.test_provider(profile_id)

    frontend_root = frontend_dist()
    if frontend_root.is_dir():
        assets = frontend_root / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            candidate = (frontend_root / path).resolve()
            if path and candidate.is_file() and frontend_root.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(frontend_root / "index.html")

    return app


def _prompt_view(service: InkFlowService, row) -> dict[str, Any]:
    return {
        **row_dict(row),
        "entity_path": service.prompts.entity_path(row),
        "editable_file": service.prompts.editable_file(row),
    }
