from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from inkflow.__about__ import __version__
from inkflow.domain import ExecutorKind, HandoffCore, PromptStage, ReferenceKind, ReviewState
from inkflow.paths import AppPaths
from inkflow.resources import frontend_dist
from inkflow.runtime_logging import ai_audit_path
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


class SourceUpdate(StrictModel):
    content: str = Field(min_length=1)


class StartPreparation(StrictModel):
    executor: ExecutorKind = ExecutorKind.EXTERNAL
    provider_profile_id: str | None = None


class JobSubmission(StrictModel):
    attempt_id: str
    lease_token: str
    result: dict[str, Any]


class RuleCreate(StrictModel):
    name: str
    body: str
    activate: bool = False


class PromptSave(StrictModel):
    name: str
    system_prompt: str
    user_template: str


class GenerationStart(StrictModel):
    executor: ExecutorKind = ExecutorKind.EXTERNAL
    rule_id: str | None = None
    provider_profile_id: str | None = None


class ComparisonStart(StrictModel):
    rule_ids: list[str]
    provider_profile_id: str


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


class ResultReview(StrictModel):
    state: ReviewState


def create_app(data_dir: Path | None = None) -> FastAPI:
    paths = AppPaths.resolve(override_data_dir=data_dir)
    service = InkFlowService(Database(paths.database_path))
    app = FastAPI(title="InkFlow", version=__version__)
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

    @app.get("/api/diagnostics/ai-audit")
    def download_ai_audit():
        path = ai_audit_path()
        if path is None or not path.is_file():
            raise HTTPException(404, "AI audit log has not been created")
        return FileResponse(
            path,
            media_type="application/x-ndjson",
            filename="inkflow-ai-audit.jsonl",
        )

    @app.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        return [row_dict(row) for row in service.projects.list()]

    @app.post("/api/projects")
    def create_project(payload: ProjectCreate) -> dict[str, str]:
        project_id = service.project_inputs.create_project(
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

    @app.get("/api/projects/{project_id}/activity")
    def project_activity(project_id: str) -> dict[str, Any]:
        return service.workflows.project_activity(project_id)

    @app.put("/api/projects/{project_id}")
    def update_project(project_id: str, payload: ProjectUpdate) -> dict[str, str]:
        service.project_inputs.update_request(project_id, payload.user_request)
        return {"project_id": project_id}

    @app.post("/api/projects/{project_id}/sources")
    def add_source(project_id: str, payload: SourceCreate) -> dict[str, str]:
        if payload.url:
            source_id = service.project_inputs.add_url_source(project_id, payload.url)
        else:
            source_id = service.project_inputs.add_source(
                project_id,
                content=str(payload.content),
                kind="pasted",
                provenance={},
            )
        return {"source_id": source_id}

    @app.put("/api/projects/{project_id}/sources/{source_id}")
    def update_source(
        project_id: str, source_id: str, payload: SourceUpdate
    ) -> dict[str, str]:
        service.project_inputs.update_source(project_id, source_id, payload.content)
        return {"source_id": source_id}

    @app.post("/api/references/import-100x")
    def import_references(payload: ImportRequest) -> dict[str, object]:
        return service.project_inputs.import_100x(payload.library_root).as_dict()

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
        job_id = service.jobs.start_preparation(
            project_id,
            executor=payload.executor,
            provider_profile_id=payload.provider_profile_id,
        )
        if payload.executor is ExecutorKind.API:
            background_tasks.add_task(service.jobs.run_api_jobs, project_id)
        return {"job_id": job_id}

    @app.get("/api/jobs/next")
    def next_job(project_id: str | None = None) -> dict[str, Any] | None:
        envelope = service.jobs.lease_external(project_id)
        return envelope.model_dump(mode="json") if envelope else None

    @app.post("/api/jobs/{job_id}/submit")
    def submit_job(job_id: str, payload: JobSubmission) -> dict[str, str]:
        service.jobs.submit_result(
            job_id,
            attempt_id=payload.attempt_id,
            lease_token=payload.lease_token,
            raw_response=json.dumps(payload.result, ensure_ascii=False, separators=(",", ":")),
        )
        return {"job_id": job_id, "status": "succeeded"}

    @app.post("/api/jobs/{job_id}/retry")
    def retry_job(job_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
        job = service.jobs.retry(job_id)
        if job.executor == ExecutorKind.API.value:
            background_tasks.add_task(service.jobs.run_api_jobs, job.project_id)
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
        return row_dict(service.handoffs.revise(project_id, payload))

    @app.post("/api/projects/{project_id}/handoff/approve")
    def approve_handoff(project_id: str) -> dict[str, Any]:
        return row_dict(service.handoffs.approve(project_id))

    @app.get("/api/projects/{project_id}/handoff/render")
    def render_handoff(project_id: str, rule_id: str | None = None) -> dict[str, str]:
        return {"content": service.handoffs.render(project_id, rule_id=rule_id)}

    @app.get("/api/rules")
    def list_rules() -> list[dict[str, Any]]:
        return [row_dict(row) for row in service.library.list_rules()]

    @app.post("/api/rules")
    def add_rule(payload: RuleCreate) -> dict[str, Any]:
        return row_dict(
            service.library.add_rule(
                name=payload.name, body=payload.body, activate=payload.activate
            )
        )

    @app.post("/api/rules/{rule_id}/activate")
    def activate_rule(rule_id: str) -> dict[str, Any]:
        return row_dict(service.library.activate_rule(rule_id))

    @app.get("/api/prompts")
    def list_prompts(stage: PromptStage | None = None) -> list[dict[str, Any]]:
        return [_prompt_view(prompt) for prompt in service.prompts.list(stage)]

    @app.put("/api/prompts/{stage}")
    def save_prompt(stage: PromptStage, payload: PromptSave) -> dict[str, Any]:
        prompt = service.prompts.save(stage=stage, **payload.model_dump())
        return _prompt_view(prompt)

    @app.post("/api/projects/{project_id}/generate")
    async def start_generation(
        project_id: str,
        payload: GenerationStart,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        experiment_id = service.experiments.start_generation(
            project_id,
            executor=payload.executor,
            rule_id=payload.rule_id,
            provider_profile_id=payload.provider_profile_id,
        )
        if payload.executor is ExecutorKind.API:
            background_tasks.add_task(service.jobs.run_api_jobs, project_id)
        return {"experiment_id": experiment_id}

    @app.post("/api/projects/{project_id}/batch-five")
    async def batch_five(
        project_id: str,
        payload: GenerationStart,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        experiment_id = service.experiments.start_generation(
            project_id,
            executor=payload.executor,
            rule_id=payload.rule_id,
            batch_five=True,
            provider_profile_id=payload.provider_profile_id,
        )
        if payload.executor is ExecutorKind.API:
            background_tasks.add_task(service.jobs.run_api_jobs, project_id)
        return {"experiment_id": experiment_id}

    @app.post("/api/projects/{project_id}/compare-rules")
    async def compare_rules(
        project_id: str,
        payload: ComparisonStart,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        experiment_id = service.experiments.start_rule_comparison(
            project_id,
            rule_ids=payload.rule_ids,
            provider_profile_id=payload.provider_profile_id,
        )
        background_tasks.add_task(service.jobs.run_api_jobs, project_id)
        return {"experiment_id": experiment_id}

    @app.get("/api/experiments/{experiment_id}")
    def experiment_detail(experiment_id: str) -> dict[str, Any]:
        return service.result_queries.experiment_detail(experiment_id)

    @app.get("/api/projects/{project_id}/results")
    def list_results(project_id: str) -> list[dict[str, Any]]:
        return service.result_queries.list(project_id)

    @app.put("/api/results/{generation_id}/review")
    def review_result(generation_id: str, payload: ResultReview) -> dict[str, Any]:
        service.results.review(generation_id, payload.state)
        return next(
            item
            for item in service.result_queries.list(service.results.get(generation_id).project_id)
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
        profile_id = service.provider_runtime.configure(**payload.model_dump())
        return {"provider_profile_id": profile_id}

    @app.post("/api/providers/{profile_id}/activate")
    def activate_provider(profile_id: str) -> dict[str, Any]:
        return row_dict(service.providers.activate(profile_id), omit={"secret_key_name"})

    @app.post("/api/providers/{profile_id}/test")
    async def test_provider(profile_id: str) -> dict[str, Any]:
        return await service.provider_runtime.test(profile_id)

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


def _prompt_view(prompt) -> dict[str, Any]:
    return prompt.model_dump(mode="json")
