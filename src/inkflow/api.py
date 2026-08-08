from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from inkflow.domain import ExecutorKind, HandoffCore, ReferenceKind
from inkflow.paths import AppPaths
from inkflow.resources import frontend_dist
from inkflow.service import InkFlowService
from inkflow.storage import Database


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(StrictModel):
    title: str
    user_request: str
    materials: list[str] = Field(default_factory=list)


class SourceCreate(StrictModel):
    content: str


class StartJob(StrictModel):
    executor: ExecutorKind = ExecutorKind.EXTERNAL
    run: bool = False


class JobSubmission(StrictModel):
    lease_token: str
    result: dict[str, Any]


class RuleCreate(StrictModel):
    name: str
    body: str
    activate: bool = False


class GenerationStart(StartJob):
    rule_id: str | None = None
    batch_five: bool = False
    provider_profile_id: str | None = None


class ComparisonStart(StartJob):
    rule_ids: list[str]
    provider_profile_id: str | None = None


class ProviderConfigure(StrictModel):
    name: str
    adapter: str
    base_url: str
    model: str
    api_key: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    activate: bool = True


class ImportRequest(StrictModel):
    library_root: str


def create_app(data_dir: Path | None = None) -> FastAPI:
    paths = AppPaths.resolve(override_data_dir=data_dir)
    service = InkFlowService(Database(paths.database_path))
    app = FastAPI(title="InkFlow", version="0.2.0")
    app.state.paths = paths
    app.state.service = service

    @app.exception_handler(FileNotFoundError)
    async def not_found_handler(_request, exc: FileNotFoundError):
        return _json_error(404, str(exc))

    @app.exception_handler(ValueError)
    async def value_error_handler(_request, exc: ValueError):
        return _json_error(400, str(exc))

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": "0.2.0", "database": str(paths.database_path)}

    @app.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        return [_row(row) for row in service.repository.list_projects()]

    @app.post("/api/projects")
    def create_project(payload: ProjectCreate) -> dict[str, str]:
        project_id = service.create_project(
            title=payload.title,
            user_request=payload.user_request,
            materials=[("", material) for material in payload.materials],
        )
        return {"project_id": project_id}

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        return {
            "project": _row(service.repository.get_project(project_id)),
            "sources": [_row(row) for row in service.repository.list_sources(project_id)],
            "jobs": [
                _row(row, omit={"payload_json", "result_json", "lease_token"})
                for row in service.repository.list_jobs(project_id)
            ],
            "experiments": [_row(row) for row in service.repository.list_experiments(project_id)],
        }

    @app.post("/api/projects/{project_id}/sources")
    def add_source(project_id: str, payload: SourceCreate) -> dict[str, str]:
        source_id = service.add_source(
            project_id,
            content=payload.content,
            kind="pasted",
            provenance={},
        )
        return {"source_id": source_id}

    @app.post("/api/references/import-100x")
    def import_references(payload: ImportRequest) -> dict[str, object]:
        return service.import_100x(Path(payload.library_root)).as_dict()

    @app.get("/api/references")
    def list_references(kind: ReferenceKind | None = None) -> list[dict[str, Any]]:
        return [
            _row(row, omit={"body", "metadata_json"})
            for row in service.repository.list_references(kind=kind)
        ]

    @app.post("/api/projects/{project_id}/prepare")
    async def start_preparation(project_id: str, payload: StartJob) -> dict[str, str]:
        job_id = service.start_preparation(project_id, executor=payload.executor)
        if payload.run:
            if payload.executor is not ExecutorKind.API:
                raise HTTPException(400, "run 仅适用于 API 执行器")
            await service.run_api_jobs(project_id)
        return {"job_id": job_id}

    @app.get("/api/jobs/next")
    def next_job(project_id: str | None = None) -> dict[str, Any] | None:
        envelope = service.lease_external_job(project_id)
        return envelope.model_dump(mode="json") if envelope else None

    @app.post("/api/jobs/{job_id}/submit")
    def submit_job(job_id: str, payload: JobSubmission) -> dict[str, str]:
        service.submit_job(job_id, lease_token=payload.lease_token, result=payload.result)
        return {"job_id": job_id, "status": "succeeded"}

    @app.post("/api/jobs/{job_id}/retry")
    def retry_job(job_id: str) -> dict[str, Any]:
        return _row(service.repository.fail_job(job_id, error="", retry=True))

    @app.get("/api/projects/{project_id}/handoff")
    def get_handoff(project_id: str) -> dict[str, Any]:
        row = service.repository.get_handoff(project_id)
        return {"handoff": _row(row), "core": service.repository.handoff_core(row).model_dump()}

    @app.put("/api/projects/{project_id}/handoff")
    def revise_handoff(project_id: str, payload: HandoffCore) -> dict[str, Any]:
        return _row(service.revise_handoff(project_id, payload))

    @app.post("/api/projects/{project_id}/handoff/approve")
    def approve_handoff(project_id: str) -> dict[str, Any]:
        return _row(service.approve_handoff(project_id))

    @app.get("/api/projects/{project_id}/handoff/render")
    def render_handoff(project_id: str, rule_id: str | None = None) -> dict[str, str]:
        return {"content": service.render_handoff(project_id, rule_id=rule_id)}

    @app.get("/api/rules")
    def list_rules() -> list[dict[str, Any]]:
        return [_row(row) for row in service.repository.list_rules()]

    @app.post("/api/rules")
    def add_rule(payload: RuleCreate) -> dict[str, Any]:
        return _row(
            service.add_rule(name=payload.name, body=payload.body, activate=payload.activate)
        )

    @app.post("/api/rules/{rule_id}/activate")
    def activate_rule(rule_id: str) -> dict[str, Any]:
        return _row(service.activate_rule(rule_id))

    @app.post("/api/projects/{project_id}/generate")
    async def start_generation(project_id: str, payload: GenerationStart) -> dict[str, str]:
        experiment_id = service.start_generation(
            project_id,
            executor=payload.executor,
            rule_id=payload.rule_id,
            batch_five=payload.batch_five,
            provider_profile_id=payload.provider_profile_id,
        )
        if payload.run:
            if payload.executor is not ExecutorKind.API:
                raise HTTPException(400, "run 仅适用于 API 执行器")
            await service.run_api_jobs(project_id)
        return {"experiment_id": experiment_id}

    @app.post("/api/projects/{project_id}/compare-rules")
    async def compare_rules(project_id: str, payload: ComparisonStart) -> dict[str, str]:
        experiment_id = service.start_rule_comparison(
            project_id,
            executor=payload.executor,
            rule_ids=payload.rule_ids,
            provider_profile_id=payload.provider_profile_id,
        )
        if payload.run:
            if payload.executor is not ExecutorKind.API:
                raise HTTPException(400, "run 仅适用于 API 执行器")
            await service.run_api_jobs(project_id)
        return {"experiment_id": experiment_id}

    @app.get("/api/projects/{project_id}/results")
    def list_results(project_id: str) -> list[dict[str, Any]]:
        return [
            _row(row, omit={"raw_response"})
            for row in service.repository.list_generations(project_id)
        ]

    @app.post("/api/results/{generation_id}/select")
    def select_result(generation_id: str) -> dict[str, Any]:
        return _row(service.repository.select_generation(generation_id), omit={"raw_response"})

    @app.post("/api/providers")
    def configure_provider(payload: ProviderConfigure) -> dict[str, str]:
        profile_id = service.configure_provider(**payload.model_dump())
        return {"provider_profile_id": profile_id}

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


def _row(row: Any, *, omit: set[str] | None = None) -> dict[str, Any]:
    excluded = omit or set()
    result: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.name in excluded:
            continue
        value = getattr(row, column.name)
        if column.name.endswith("_json") and value:
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        result[column.name] = value
    return result


def _json_error(status: int, message: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status, content={"detail": message})
