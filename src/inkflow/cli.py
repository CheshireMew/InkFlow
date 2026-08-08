from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import typer

from inkflow.domain import ExecutorKind, HandoffCore, ReferenceKind
from inkflow.paths import AppPaths
from inkflow.service import InkFlowService
from inkflow.storage import Database

app = typer.Typer(help="InkFlow 本地写作工作台", no_args_is_help=True)
project_app = typer.Typer(help="写作项目")
reference_app = typer.Typer(help="参考案例与钩子")
prepare_app = typer.Typer(help="写作准备")
job_app = typer.Typer(help="外部执行任务")
handoff_app = typer.Typer(help="两轮写作交接")
rule_app = typer.Typer(help="写作规则")
generate_app = typer.Typer(help="成品生成")
experiment_app = typer.Typer(help="提示词对比实验")
result_app = typer.Typer(help="生成结果")
provider_app = typer.Typer(help="API 提供方")

app.add_typer(project_app, name="project")
app.add_typer(reference_app, name="reference")
app.add_typer(prepare_app, name="prepare")
app.add_typer(job_app, name="job")
app.add_typer(handoff_app, name="handoff")
app.add_typer(rule_app, name="rule")
app.add_typer(generate_app, name="generate")
app.add_typer(experiment_app, name="experiment")
app.add_typer(result_app, name="result")
app.add_typer(provider_app, name="provider")


@app.callback()
def configure(
    ctx: typer.Context,
    data_dir: Path | None = typer.Option(None, "--data-dir", envvar="INKFLOW_DATA_DIR"),
) -> None:
    paths = AppPaths.resolve(override_data_dir=data_dir)
    ctx.obj = {"paths": paths, "service": InkFlowService(Database(paths.database_path))}


@app.command()
def doctor(ctx: typer.Context) -> None:
    paths: AppPaths = ctx.obj["paths"]
    service = _service(ctx)
    _emit(
        {
            "ok": True,
            "database": str(paths.database_path),
            "projects": len(service.repository.list_projects()),
            "references": len(service.repository.list_references()),
            "rules": len(service.repository.list_rules()),
        }
    )


@app.command("app")
def app_server(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    import threading
    import webbrowser

    import uvicorn

    from inkflow.api import create_app

    paths: AppPaths = ctx.obj["paths"]
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(create_app(paths.data_dir), host=host, port=port)


@project_app.command("create")
def project_create(
    ctx: typer.Context,
    title: str = typer.Option(..., "--title"),
    request: str | None = typer.Option(None, "--request"),
    request_file: Path | None = typer.Option(None, "--request-file"),
    material: list[str] | None = typer.Option(None, "--material"),
    material_file: list[Path] | None = typer.Option(None, "--material-file"),
) -> None:
    user_request = _text_argument(request, request_file, "request")
    materials: list[tuple[str, str]] = [("", item) for item in (material or []) if item.strip()]
    for path in material_file or []:
        materials.append((path.name, path.read_text(encoding="utf-8-sig")))
    project_id = _service(ctx).create_project(
        title=title, user_request=user_request, materials=materials
    )
    _emit({"project_id": project_id})


@project_app.command("list")
def project_list(ctx: typer.Context) -> None:
    _emit([_row(row) for row in _service(ctx).repository.list_projects()])


@project_app.command("show")
def project_show(ctx: typer.Context, project_id: str) -> None:
    service = _service(ctx)
    _emit(
        {
            "project": _row(service.repository.get_project(project_id)),
            "sources": [
                _row(row, omit={"content"}) for row in service.repository.list_sources(project_id)
            ],
            "jobs": [
                _row(row, omit={"payload_json", "result_json", "lease_token"})
                for row in service.repository.list_jobs(project_id)
            ],
            "experiments": [_row(row) for row in service.repository.list_experiments(project_id)],
        }
    )


@project_app.command("add-source")
def project_add_source(
    ctx: typer.Context,
    project_id: str,
    text: str | None = typer.Option(None, "--text"),
    file: Path | None = typer.Option(None, "--file"),
) -> None:
    content = _text_argument(text, file, "source")
    source_id = _service(ctx).add_source(
        project_id,
        content=content,
        kind="file" if file else "pasted",
        provenance={"source_name": file.name} if file else {},
    )
    _emit({"source_id": source_id})


@reference_app.command("import-100x")
def reference_import_100x(ctx: typer.Context, library_root: Path) -> None:
    _emit(_service(ctx).import_100x(library_root).as_dict())


@reference_app.command("list")
def reference_list(
    ctx: typer.Context,
    kind: ReferenceKind | None = typer.Option(None, "--kind"),
) -> None:
    rows = _service(ctx).repository.list_references(kind=kind)
    _emit([_row(row, omit={"body", "metadata_json"}) for row in rows])


@prepare_app.command("start")
def prepare_start(
    ctx: typer.Context,
    project_id: str,
    executor: ExecutorKind = typer.Option(ExecutorKind.EXTERNAL, "--executor"),
    run: bool = typer.Option(False, "--run"),
) -> None:
    service = _service(ctx)
    job_id = service.start_preparation(project_id, executor=executor)
    if run:
        if executor is not ExecutorKind.API:
            raise typer.BadParameter("--run 仅适用于 API 执行器")
        asyncio.run(service.run_api_jobs(project_id))
    _emit({"job_id": job_id, "executor": executor.value})


@job_app.command("next")
def job_next(ctx: typer.Context, project_id: str | None = typer.Option(None, "--project")) -> None:
    envelope = _service(ctx).lease_external_job(project_id)
    _emit(envelope.model_dump(mode="json") if envelope else None)


@job_app.command("submit")
def job_submit(
    ctx: typer.Context,
    job_id: str,
    lease_token: str = typer.Option(..., "--lease-token"),
    result: str | None = typer.Option(None, "--result"),
    result_file: Path | None = typer.Option(None, "--result-file"),
) -> None:
    raw = _text_argument(result, result_file, "result")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise typer.BadParameter("result 必须是 JSON 对象")
    _service(ctx).submit_job(job_id, lease_token=lease_token, result=parsed)
    _emit({"job_id": job_id, "status": "succeeded"})


@job_app.command("retry")
def job_retry(ctx: typer.Context, job_id: str) -> None:
    row = _service(ctx).repository.fail_job(job_id, error="", retry=True)
    _emit(_row(row, omit={"payload_json", "result_json", "lease_token"}))


@handoff_app.command("show")
def handoff_show(ctx: typer.Context, project_id: str) -> None:
    service = _service(ctx)
    row = service.repository.get_handoff(project_id)
    _emit(
        {
            "handoff": _row(row, omit={"reference_cases_json", "reference_hooks_json"}),
            "core": service.repository.handoff_core(row).model_dump(),
        }
    )


@handoff_app.command("approve")
def handoff_approve(ctx: typer.Context, project_id: str) -> None:
    _emit(_row(_service(ctx).approve_handoff(project_id)))


@handoff_app.command("revise")
def handoff_revise(
    ctx: typer.Context,
    project_id: str,
    material_file: Path = typer.Option(..., "--material-file"),
    other_inputs_file: Path | None = typer.Option(None, "--other-inputs-file"),
) -> None:
    service = _service(ctx)
    project = service.repository.get_project(project_id)
    latest = service.repository.get_handoff(project_id)
    current = service.repository.handoff_core(latest)
    row = service.revise_handoff(
        project_id,
        HandoffCore(
            user_request=project.user_request,
            purified_material=material_file.read_text(encoding="utf-8-sig"),
            reference_cases=current.reference_cases,
            reference_hooks=current.reference_hooks,
            other_inputs=(
                other_inputs_file.read_text(encoding="utf-8-sig")
                if other_inputs_file
                else current.other_inputs
            ),
        ),
    )
    _emit(_row(row))


@handoff_app.command("render")
def handoff_render(
    ctx: typer.Context,
    project_id: str,
    rule_id: str | None = typer.Option(None, "--rule"),
) -> None:
    typer.echo(_service(ctx).render_handoff(project_id, rule_id=rule_id))


@rule_app.command("add")
def rule_add(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name"),
    text: str | None = typer.Option(None, "--text"),
    file: Path | None = typer.Option(None, "--file"),
    activate: bool = typer.Option(False, "--activate"),
) -> None:
    _emit(
        _row(
            _service(ctx).add_rule(
                name=name, body=_text_argument(text, file, "rule"), activate=activate
            )
        )
    )


@rule_app.command("list")
def rule_list(ctx: typer.Context) -> None:
    _emit([_row(row) for row in _service(ctx).repository.list_rules()])


@rule_app.command("activate")
def rule_activate(ctx: typer.Context, rule_id: str) -> None:
    _emit(_row(_service(ctx).activate_rule(rule_id)))


@generate_app.command("start")
def generate_start(
    ctx: typer.Context,
    project_id: str,
    executor: ExecutorKind = typer.Option(ExecutorKind.EXTERNAL, "--executor"),
    rule_id: str | None = typer.Option(None, "--rule"),
    batch_five: bool = typer.Option(False, "--batch-five"),
    provider_profile_id: str | None = typer.Option(None, "--provider"),
    run: bool = typer.Option(False, "--run"),
) -> None:
    service = _service(ctx)
    experiment_id = service.start_generation(
        project_id,
        executor=executor,
        rule_id=rule_id,
        batch_five=batch_five,
        provider_profile_id=provider_profile_id,
    )
    if run:
        if executor is not ExecutorKind.API:
            raise typer.BadParameter("--run 仅适用于 API 执行器")
        asyncio.run(service.run_api_jobs(project_id))
    _emit({"experiment_id": experiment_id})


@experiment_app.command("compare-rules")
def experiment_compare_rules(
    ctx: typer.Context,
    project_id: str,
    rule_id: list[str] = typer.Option(..., "--rule"),
    executor: ExecutorKind = typer.Option(ExecutorKind.EXTERNAL, "--executor"),
    provider_profile_id: str | None = typer.Option(None, "--provider"),
    run: bool = typer.Option(False, "--run"),
) -> None:
    service = _service(ctx)
    experiment_id = service.start_rule_comparison(
        project_id,
        executor=executor,
        rule_ids=rule_id,
        provider_profile_id=provider_profile_id,
    )
    if run:
        if executor is not ExecutorKind.API:
            raise typer.BadParameter("--run 仅适用于 API 执行器")
        asyncio.run(service.run_api_jobs(project_id))
    _emit({"experiment_id": experiment_id})


@result_app.command("list")
def result_list(ctx: typer.Context, project_id: str) -> None:
    _emit(
        [
            _row(row, omit={"raw_response"})
            for row in _service(ctx).repository.list_generations(project_id)
        ]
    )


@result_app.command("select")
def result_select(ctx: typer.Context, generation_id: str) -> None:
    _emit(_row(_service(ctx).repository.select_generation(generation_id), omit={"raw_response"}))


@result_app.command("export")
def result_export(ctx: typer.Context, generation_id: str, output: Path) -> None:
    row = _service(ctx).repository.get_generation(generation_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(row.content + "\n", encoding="utf-8")
    _emit({"generation_id": generation_id, "output": str(output.resolve())})


@provider_app.command("configure")
def provider_configure(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name"),
    adapter: str = typer.Option(..., "--adapter"),
    base_url: str = typer.Option(..., "--base-url"),
    model: str = typer.Option(..., "--model"),
    api_key: str = typer.Option(..., "--api-key", hide_input=True),
    parameters: str = typer.Option("{}", "--parameters"),
    activate: bool = typer.Option(True, "--activate/--no-activate"),
) -> None:
    parsed = json.loads(parameters)
    if not isinstance(parsed, dict):
        raise typer.BadParameter("parameters 必须是 JSON 对象")
    profile_id = _service(ctx).configure_provider(
        name=name,
        adapter=adapter,
        base_url=base_url,
        model=model,
        api_key=api_key,
        parameters=parsed,
        activate=activate,
    )
    _emit({"provider_profile_id": profile_id})


def _service(ctx: typer.Context) -> InkFlowService:
    return ctx.obj["service"]


def _text_argument(value: str | None, path: Path | None, label: str) -> str:
    if value is not None and path is not None:
        raise typer.BadParameter(f"{label} 不能同时从文本和文件读取")
    if path is not None:
        return path.read_text(encoding="utf-8-sig").strip()
    if value is not None:
        return value.strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise typer.BadParameter(f"缺少 {label}")


def _row(row: Any, *, omit: set[str] | None = None) -> dict[str, Any]:
    excluded = omit or set()
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in excluded
    }


def _emit(value: Any) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
