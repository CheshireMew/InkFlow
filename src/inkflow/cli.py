from __future__ import annotations

import asyncio
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any

import typer

from inkflow.domain import ExecutorKind, HandoffCore, PromptStage, ReferenceKind, ReviewState
from inkflow.paths import AppPaths
from inkflow.resources import frontend_dist
from inkflow.serialization import row_dict
from inkflow.service import InkFlowService
from inkflow.storage import Database

app = typer.Typer(help="InkFlow 本地写作工作台", no_args_is_help=True)
project_app = typer.Typer(help="写作项目")
reference_app = typer.Typer(help="参考案例与钩子")
prepare_app = typer.Typer(help="写作准备")
job_app = typer.Typer(help="外部执行任务")
handoff_app = typer.Typer(help="写作交接")
rule_app = typer.Typer(help="写作规则")
prompt_app = typer.Typer(help="各环节当前提示词")
generate_app = typer.Typer(help="单篇生成")
experiment_app = typer.Typer(help="批量与规则对比实验")
result_app = typer.Typer(help="生成结果")
provider_app = typer.Typer(help="模型 API 提供方")

for name, group in {
    "project": project_app,
    "reference": reference_app,
    "prepare": prepare_app,
    "job": job_app,
    "handoff": handoff_app,
    "rule": rule_app,
    "prompt": prompt_app,
    "generate": generate_app,
    "experiment": experiment_app,
    "result": result_app,
    "provider": provider_app,
}.items():
    app.add_typer(group, name=name)


@app.callback()
def configure(
    ctx: typer.Context,
    data_dir: Path | None = typer.Option(None, "--data-dir", envvar="INKFLOW_DATA_DIR"),
) -> None:
    paths = AppPaths.resolve(override_data_dir=data_dir)
    ctx.obj = {"paths": paths}


@app.command()
def doctor(ctx: typer.Context) -> None:
    diagnostics = _service(ctx).doctor()
    diagnostics["frontend_assets"] = frontend_dist().is_dir()
    _emit(diagnostics)


@app.command("app")
def app_server(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(0, "--port", min=0, max=65535),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    import threading
    import urllib.request
    import webbrowser

    import uvicorn

    from inkflow.api import create_app

    paths: AppPaths = ctx.obj["paths"]
    server_socket = _bind_server_socket(host, port)
    actual_port = int(server_socket.getsockname()[1])
    url = f"http://{host}:{actual_port}"
    typer.echo(json.dumps({"url": url}, ensure_ascii=False), err=True)
    if open_browser:
        browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        browser_url = f"http://{browser_host}:{actual_port}"

        def open_when_ready() -> None:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(
                        f"{browser_url}/api/health", timeout=0.5
                    ) as response:
                        if response.status == 200:
                            webbrowser.open(browser_url)
                            return
                except OSError:
                    time.sleep(0.1)

        threading.Thread(target=open_when_ready, daemon=True).start()
    config = uvicorn.Config(create_app(paths.data_dir), host=host, port=actual_port)
    server = uvicorn.Server(config)
    try:
        server.run(sockets=[server_socket])
    finally:
        server_socket.close()


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
    materials: list[tuple[str, str]] = [("", item) for item in material or []]
    for path in material_file or []:
        materials.append((path.name, path.read_text(encoding="utf-8-sig")))
    project_id = _service(ctx).project_inputs.create_project(
        title=title, user_request=user_request, materials=materials
    )
    _emit({"project_id": project_id})


@project_app.command("list")
def project_list(ctx: typer.Context) -> None:
    _emit([row_dict(row) for row in _service(ctx).projects.list()])


@project_app.command("show")
def project_show(ctx: typer.Context, project_id: str) -> None:
    service = _service(ctx)
    jobs = service.workflows.list_jobs(project_id)
    _emit(
        {
            "project": row_dict(service.projects.get(project_id)),
            "sources": [row_dict(row) for row in service.projects.list_sources(project_id)],
            "jobs": [
                {
                    **row_dict(row),
                    "attempts": [
                        row_dict(attempt, omit={"lease_token"})
                        for attempt in service.workflows.list_attempts(row.id)
                    ],
                }
                for row in jobs
            ],
            "experiments": [
                row_dict(row) for row in service.workflows.list_experiments(project_id)
            ],
        }
    )


@project_app.command("add-source")
def project_add_source(
    ctx: typer.Context,
    project_id: str,
    text: str | None = typer.Option(None, "--text"),
    file: Path | None = typer.Option(None, "--file"),
    url: str | None = typer.Option(None, "--url"),
) -> None:
    if url:
        if text is not None or file is not None:
            raise typer.BadParameter("URL、文本和文件只能选择一种")
        source_id = _service(ctx).project_inputs.add_url_source(project_id, url)
    else:
        content = _text_argument(text, file, "source")
        source_id = _service(ctx).project_inputs.add_source(
            project_id,
            content=content,
            kind="file" if file else "pasted",
            provenance={"source_name": file.name} if file else {},
        )
    _emit({"source_id": source_id})


@reference_app.command("import-100x")
def reference_import_100x(ctx: typer.Context, library_root: Path) -> None:
    _emit(_service(ctx).project_inputs.import_100x(library_root).as_dict())


@reference_app.command("list")
def reference_list(
    ctx: typer.Context,
    kind: ReferenceKind | None = typer.Option(None, "--kind"),
    include_inactive: bool = typer.Option(False, "--include-inactive"),
) -> None:
    rows = _service(ctx).library.list_references(kind=kind, include_inactive=include_inactive)
    _emit([{**row_dict(row, omit={"body"}), "body_preview": row.body[:180]} for row in rows])


@reference_app.command("get")
def reference_get(ctx: typer.Context, reference_id: str) -> None:
    _emit(row_dict(_service(ctx).library.get_reference(reference_id)))


@prepare_app.command("start")
def prepare_start(
    ctx: typer.Context,
    project_id: str,
    executor: ExecutorKind = typer.Option(ExecutorKind.EXTERNAL, "--executor"),
    provider_profile_id: str | None = typer.Option(None, "--provider"),
) -> None:
    service = _service(ctx)
    job_id = service.jobs.start_preparation(
        project_id,
        executor=executor,
        provider_profile_id=provider_profile_id,
    )
    if executor is ExecutorKind.API:
        asyncio.run(service.jobs.run_api_jobs(project_id))
    _emit({"job_id": job_id, "executor": executor.value})


@job_app.command("next")
def job_next(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    del json_output
    envelope = _service(ctx).jobs.lease_external(project_id)
    _emit(envelope.model_dump(mode="json") if envelope else None)


@job_app.command("submit")
def job_submit(
    ctx: typer.Context,
    job_id: str,
    attempt_id: str = typer.Option(..., "--attempt-id"),
    lease_token: str = typer.Option(..., "--lease-token"),
    result: str | None = typer.Option(None, "--result"),
    result_file: Path | None = typer.Option(None, "--result-file"),
) -> None:
    raw = _text_argument(result, result_file, "result")
    _service(ctx).jobs.submit_result(
        job_id,
        attempt_id=attempt_id,
        lease_token=lease_token,
        raw_response=raw,
    )
    _emit({"job_id": job_id, "attempt_id": attempt_id, "status": "succeeded"})


@job_app.command("retry")
def job_retry(ctx: typer.Context, job_id: str) -> None:
    service = _service(ctx)
    job = service.jobs.retry(job_id)
    if job.executor == ExecutorKind.API.value:
        asyncio.run(service.jobs.run_api_jobs(job.project_id))
    _emit({"job_id": job_id, "status": "pending"})


@handoff_app.command("show")
def handoff_show(
    ctx: typer.Context,
    project_id: str,
    markdown: bool = typer.Option(False, "--markdown"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    if markdown and json_output:
        raise typer.BadParameter("--markdown 与 --json 不能同时使用")
    service = _service(ctx)
    if markdown:
        typer.echo(service.handoffs.render(project_id))
        return
    row = service.workflows.get_handoff(project_id)
    _emit(
        {
            "handoff": row_dict(row, omit={"reference_cases_json", "reference_hooks_json"}),
            "core": service.workflows.handoff_core(row).model_dump(),
        }
    )


@handoff_app.command("approve")
def handoff_approve(ctx: typer.Context, project_id: str) -> None:
    _emit(row_dict(_service(ctx).handoffs.approve(project_id)))


@handoff_app.command("revise")
def handoff_revise(
    ctx: typer.Context,
    project_id: str,
    file: Path = typer.Option(..., "--file"),
) -> None:
    core = HandoffCore.model_validate_json(file.read_text(encoding="utf-8-sig"))
    _emit(row_dict(_service(ctx).handoffs.revise(project_id, core)))


@rule_app.command("add")
def rule_add(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name"),
    text: str | None = typer.Option(None, "--text"),
    file: Path | None = typer.Option(None, "--file"),
    activate: bool = typer.Option(False, "--activate"),
) -> None:
    _emit(
        row_dict(
            _service(ctx).library.add_rule(
                name=name, body=_text_argument(text, file, "rule"), activate=activate
            )
        )
    )


@rule_app.command("list")
def rule_list(ctx: typer.Context) -> None:
    _emit([row_dict(row) for row in _service(ctx).library.list_rules()])


@rule_app.command("activate")
def rule_activate(ctx: typer.Context, rule_id: str) -> None:
    _emit(row_dict(_service(ctx).library.activate_rule(rule_id)))


@prompt_app.command("list")
def prompt_list(
    ctx: typer.Context,
    stage: PromptStage | None = typer.Option(None, "--stage"),
) -> None:
    service = _service(ctx)
    _emit([_prompt_view(prompt) for prompt in service.prompts.list(stage)])


@prompt_app.command("set")
def prompt_set(
    ctx: typer.Context,
    stage: PromptStage = typer.Option(..., "--stage"),
    name: str = typer.Option(..., "--name"),
    system_file: Path = typer.Option(..., "--system-file"),
    template_file: Path = typer.Option(..., "--template-file"),
) -> None:
    service = _service(ctx)
    row = service.prompts.save(
        stage=stage,
        name=name,
        system_prompt=system_file.read_text(encoding="utf-8-sig"),
        user_template=template_file.read_text(encoding="utf-8-sig"),
    )
    _emit(_prompt_view(row))


@generate_app.command("start")
def generate_start(
    ctx: typer.Context,
    project_id: str,
    executor: ExecutorKind = typer.Option(ExecutorKind.EXTERNAL, "--executor"),
    rule_id: str | None = typer.Option(None, "--rule"),
    provider_profile_id: str | None = typer.Option(None, "--provider"),
) -> None:
    _start_generation_command(
        ctx,
        project_id,
        executor=executor,
        rule_id=rule_id,
        provider_profile_id=provider_profile_id,
        batch_five=False,
    )


@experiment_app.command("batch-five")
def experiment_batch_five(
    ctx: typer.Context,
    project_id: str,
    executor: ExecutorKind = typer.Option(ExecutorKind.EXTERNAL, "--executor"),
    rule_id: str | None = typer.Option(None, "--rule"),
    provider_profile_id: str | None = typer.Option(None, "--provider"),
) -> None:
    _start_generation_command(
        ctx,
        project_id,
        executor=executor,
        rule_id=rule_id,
        provider_profile_id=provider_profile_id,
        batch_five=True,
    )


@experiment_app.command("compare-rules")
def experiment_compare_rules(
    ctx: typer.Context,
    project_id: str,
    rule_id: list[str] = typer.Option(..., "--rule"),
    provider_profile_id: str = typer.Option(..., "--provider"),
) -> None:
    service = _service(ctx)
    experiment_id = service.experiments.start_rule_comparison(
        project_id,
        rule_ids=rule_id,
        provider_profile_id=provider_profile_id,
    )
    asyncio.run(service.jobs.run_api_jobs(project_id))
    _emit({"experiment_id": experiment_id, "executor": ExecutorKind.API.value})


@experiment_app.command("show")
def experiment_show(ctx: typer.Context, experiment_id: str) -> None:
    _emit(_service(ctx).result_queries.experiment_detail(experiment_id))


@result_app.command("list")
def result_list(ctx: typer.Context, project_id: str) -> None:
    _emit(_service(ctx).result_queries.list(project_id))


@result_app.command("review")
def result_review(
    ctx: typer.Context,
    generation_id: str,
    state: ReviewState = typer.Option(..., "--state"),
) -> None:
    row = _service(ctx).results.review(generation_id, state)
    _emit({"generation_id": generation_id, "review_state": row.review_state})


@result_app.command("edit")
def result_edit(
    ctx: typer.Context,
    generation_id: str,
    file: Path = typer.Option(..., "--file"),
) -> None:
    revision = _service(ctx).results.add_revision(
        generation_id, file.read_text(encoding="utf-8-sig")
    )
    _emit(row_dict(revision))


@result_app.command("export")
def result_export(ctx: typer.Context, generation_id: str, output: Path) -> None:
    content = _service(ctx).results.current_content(generation_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content + "\n", encoding="utf-8")
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
    profile_id = _service(ctx).provider_runtime.configure(
        name=name,
        adapter=adapter,
        base_url=base_url,
        model=model,
        api_key=api_key,
        parameters=parsed,
        activate=activate,
    )
    _emit({"provider_profile_id": profile_id})


@provider_app.command("list")
def provider_list(ctx: typer.Context) -> None:
    _emit([row_dict(row, omit={"secret_key_name"}) for row in _service(ctx).providers.list()])


@provider_app.command("test")
def provider_test(
    ctx: typer.Context,
    profile_id: str | None = typer.Option(None, "--provider"),
) -> None:
    _emit(asyncio.run(_service(ctx).provider_runtime.test(profile_id)))


@provider_app.command("activate")
def provider_activate(ctx: typer.Context, profile_id: str) -> None:
    _emit(row_dict(_service(ctx).providers.activate(profile_id), omit={"secret_key_name"}))


def _start_generation_command(
    ctx: typer.Context,
    project_id: str,
    *,
    executor: ExecutorKind,
    rule_id: str | None,
    provider_profile_id: str | None,
    batch_five: bool,
) -> None:
    service = _service(ctx)
    experiment_id = service.experiments.start_generation(
        project_id,
        executor=executor,
        rule_id=rule_id,
        batch_five=batch_five,
        provider_profile_id=provider_profile_id,
    )
    if executor is ExecutorKind.API:
        asyncio.run(service.jobs.run_api_jobs(project_id))
    _emit({"experiment_id": experiment_id})


def _service(ctx: typer.Context) -> InkFlowService:
    service = ctx.obj.get("service")
    if service is None:
        paths: AppPaths = ctx.obj["paths"]
        service = InkFlowService(Database(paths.database_path))
        ctx.obj["service"] = service
    return service


def _prompt_view(prompt) -> dict[str, Any]:
    return prompt.model_dump(mode="json")


def _text_argument(value: str | None, path: Path | None, label: str) -> str:
    if value is not None and path is not None:
        raise typer.BadParameter(f"{label} 不能同时从文本和文件读取")
    if path is not None:
        return path.read_text(encoding="utf-8-sig")
    if value is not None:
        return value
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise typer.BadParameter(f"缺少 {label}")


def _bind_server_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(128)
        return sock
    except Exception:
        sock.close()
        raise


def _emit(value: Any) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    try:
        app()
    except PermissionError as exc:
        _emit_error(exc, exit_code=3)
    except FileNotFoundError as exc:
        _emit_error(exc, exit_code=4)
    except ValueError as exc:
        _emit_error(exc, exit_code=2)
    except RuntimeError as exc:
        _emit_error(exc, exit_code=5)


def _emit_error(exc: Exception, *, exit_code: int) -> None:
    typer.echo(
        json.dumps(
            {"error": type(exc).__name__, "detail": str(exc)},
            ensure_ascii=False,
        ),
        err=True,
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
