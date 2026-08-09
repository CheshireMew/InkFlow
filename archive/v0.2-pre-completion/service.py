from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from inkflow.boundaries import sanitize_handoff_material
from inkflow.domain import (
    ExecutionPackage,
    ExecutorKind,
    ExperimentKind,
    ExperimentStatus,
    GenerationResult,
    HandoffCore,
    JobEnvelope,
    JobKind,
    PreparationResult,
    ReferenceKind,
    ReferenceSelectionResult,
    stable_hash,
)
from inkflow.providers.factory import create_provider, save_api_key
from inkflow.reference_import import ImportReport, import_100x_library
from inkflow.storage import Database, Repository
from inkflow.storage.schema import HandoffRow, JobRow, WritingRuleRow

PREPARATION_SYSTEM = """你负责为写作准备正式交接材料。只处理材料，不写成品。
净化采用删除式处理：保留足以准确成文的原文和必要上下文，删除重复、无关、只用于备查或会分散重点的内容；不要摘要、改写、补写角度或预先设计正文结构。
如果允许联网，只寻找能够补充当前材料或增强传播力的非重复新信息，不做例行核查。
purified_material 中不得出现来源名称、来源数量、原始文件名、磁盘路径、链接或引用编号。
只返回合法 JSON：{"purified_material":"...","discovered_sources":[],"other_inputs":"无"}。"""


REFERENCE_SYSTEM = """根据写作要求和净化材料，从给定索引中选择有帮助的参考写作案例与参考开头钩子。
只根据写作技巧和成品形式判断，不根据案例写了什么主题来匹配。不要规定正文结构，不要解释选择过程，也不固定选择数量。
只返回合法 JSON：{"case_ids":[],"hook_ids":[]}。"""


GENERATION_SYSTEM = """只使用给定的正式写作执行包完成写作。不得从其它对话、记忆或来源补充内容。
不要解释过程，不要评审、融合、润色或二次改写。"""


class InkFlowService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        self.repository = Repository(database)

    def import_100x(self, library_root: Path) -> ImportReport:
        return import_100x_library(self.repository, library_root)

    def create_project(
        self, *, title: str, user_request: str, materials: list[tuple[str, str]]
    ) -> str:
        project = self.repository.create_project(title=title, user_request=user_request)
        for source_name, content in materials:
            self.repository.add_source(
                project.id,
                kind="file" if source_name else "pasted",
                content=content,
                provenance={"source_name": source_name} if source_name else {},
            )
        return project.id

    def add_source(
        self, project_id: str, *, content: str, kind: str, provenance: dict[str, Any]
    ) -> str:
        return self.repository.add_source(
            project_id,
            kind=kind,
            content=content,
            provenance=provenance,
        ).id

    def start_preparation(self, project_id: str, *, executor: ExecutorKind) -> str:
        project = self.repository.get_project(project_id)
        sources = self.repository.list_sources(project_id)
        if not sources:
            raise ValueError("project has no source material")
        payload = {
            "schema_version": 1,
            "instruction": PREPARATION_SYSTEM,
            "user_request": project.user_request,
            "materials": [source.content for source in sources],
            "search": {
                "mode": "由外部执行器或具备原生搜索能力的 API 提供方执行",
                "purpose": "只发现能够补充内容或增强传播力的非重复新信息，不做例行核查",
            },
            "result_schema": PreparationResult.model_json_schema(),
            "model_input": _preparation_user_prompt(
                project.user_request, [source.content for source in sources]
            ),
        }
        job = self.repository.create_job(
            project_id=project_id,
            kind=JobKind.PREPARE_MATERIAL,
            executor=executor.value,
            payload=payload,
        )
        return job.id

    async def run_api_jobs(self, project_id: str) -> None:
        while True:
            envelope = self.repository.lease_next_job(project_id, executor=ExecutorKind.API.value)
            if envelope is None:
                return
            job = self.repository.get_job(envelope.job_id)
            try:
                result = await self._execute_api_job(envelope)
                self.submit_job(job.id, lease_token=None, result=result)
            except Exception as exc:
                self.repository.fail_job(job.id, error=str(exc), retry=False)
                if job.experiment_id:
                    self.repository.update_experiment_status(
                        job.experiment_id, ExperimentStatus.FAILED
                    )
                raise

    def lease_external_job(self, project_id: str | None = None) -> JobEnvelope | None:
        return self.repository.lease_next_job(project_id, executor=ExecutorKind.EXTERNAL.value)

    def submit_job(self, job_id: str, *, lease_token: str | None, result: dict[str, Any]) -> None:
        job = self.repository.get_job(job_id)
        if JobKind(job.kind) is JobKind.PREPARE_MATERIAL:
            parsed = PreparationResult.model_validate(result)
            sanitized = sanitize_handoff_material(parsed.purified_material)
            if not sanitized:
                raise ValueError("preparation returned empty purified material")
            normalized_result = {
                "purified_material": sanitized,
                "discovered_sources": parsed.discovered_sources,
                "other_inputs": parsed.other_inputs,
            }
            completed = self.repository.complete_job(
                job_id, lease_token=lease_token, result=normalized_result
            )
            self._save_discovered_sources(completed.project_id, parsed.discovered_sources)
            self._create_reference_selection_job(completed, normalized_result)
            return

        if JobKind(job.kind) is JobKind.SELECT_REFERENCES:
            parsed = ReferenceSelectionResult.model_validate(result)
            self._validate_reference_selection(parsed)
            completed = self.repository.complete_job(
                job_id, lease_token=lease_token, result=parsed.model_dump()
            )
            payload = json.loads(completed.payload_json)
            self.repository.create_handoff(
                completed.project_id,
                purified_material=payload["purified_material"],
                case_ids=parsed.case_ids,
                hook_ids=parsed.hook_ids,
                other_inputs=payload.get("other_inputs") or "无",
            )
            return

        parsed = GenerationResult.model_validate(result)
        payload = json.loads(job.payload_json)
        expected = int(payload["output_count"])
        if len(parsed.outputs) != expected:
            raise ValueError(
                f"generation returned {len(parsed.outputs)} outputs; expected {expected}"
            )
        if any(not output.strip() for output in parsed.outputs):
            raise ValueError("generation outputs cannot contain empty content")
        completed = self.repository.complete_job(
            job_id, lease_token=lease_token, result=parsed.model_dump()
        )
        self.repository.save_generations(
            job=completed,
            handoff_id=str(completed.handoff_id),
            writing_rule_id=str(payload["writing_rule_id"]),
            outputs=parsed.outputs,
            raw_response=parsed.raw_response,
            executor_metadata=parsed.executor_metadata,
        )
        self._advance_experiment(completed)

    def _validate_reference_selection(self, selection: ReferenceSelectionResult) -> None:
        cases = self.repository.get_references(selection.case_ids)
        hooks = self.repository.get_references(selection.hook_ids)
        if any(row.kind != ReferenceKind.CASE.value for row in cases):
            raise ValueError("case_ids can only contain case references")
        if any(row.kind != ReferenceKind.HOOK.value for row in hooks):
            raise ValueError("hook_ids can only contain hook references")
        if {row.body_hash for row in cases} & {row.body_hash for row in hooks}:
            raise ValueError("a reference cannot serve as both case and hook")

    def approve_handoff(self, project_id: str) -> HandoffRow:
        return self.repository.approve_handoff(project_id)

    def render_handoff(self, project_id: str, *, rule_id: str | None = None) -> str:
        row = self.repository.get_handoff(project_id)
        core = self.repository.handoff_core(row)
        rule = self.repository.get_rule(rule_id)
        return ExecutionPackage(handoff=core, writing_rule=rule.body).render()

    def revise_handoff(self, project_id: str, core: HandoffCore) -> HandoffRow:
        project = self.repository.get_project(project_id)
        if core.user_request != project.user_request:
            raise ValueError(
                "user request can only be changed through the project request boundary"
            )
        latest = self.repository.get_handoff(project_id)
        case_ids = json.loads(latest.reference_case_ids_json)
        hook_ids = json.loads(latest.reference_hook_ids_json)
        return self.repository.create_handoff(
            project_id,
            purified_material=sanitize_handoff_material(core.purified_material),
            case_ids=case_ids,
            hook_ids=hook_ids,
            other_inputs=core.other_inputs,
        )

    def add_rule(self, *, name: str, body: str, activate: bool = False) -> WritingRuleRow:
        return self.repository.add_rule(name=name, body=body, activate=activate)

    def activate_rule(self, rule_id: str) -> WritingRuleRow:
        return self.repository.activate_rule(rule_id)

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
        secret_key_name = f"provider:{name}"
        save_api_key(secret_key_name, api_key)
        capabilities = {
            "web_search": adapter == "openai-responses",
            "structured_output": False,
        }
        row = self.repository.save_provider_profile(
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

    def start_generation(
        self,
        project_id: str,
        *,
        executor: ExecutorKind,
        rule_id: str | None = None,
        batch_five: bool = False,
        provider_profile_id: str | None = None,
    ) -> str:
        rule = self.repository.get_rule(rule_id)
        kind = ExperimentKind.BATCH_FIVE if batch_five else ExperimentKind.SINGLE
        return self._start_experiment(
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
        executor: ExecutorKind,
        rule_ids: list[str],
        provider_profile_id: str | None = None,
    ) -> str:
        if len(rule_ids) != 5:
            raise ValueError("compare-rules requires exactly five rule revisions")
        rules = [self.repository.get_rule(rule_id) for rule_id in rule_ids]
        if len({rule.body_hash for rule in rules}) != 5:
            raise ValueError("compare-rules requires five different rule bodies")
        return self._start_experiment(
            project_id,
            kind=ExperimentKind.COMPARE_RULES,
            executor=executor,
            rules=rules,
            provider_profile_id=provider_profile_id,
        )

    async def _execute_api_job(self, envelope: JobEnvelope) -> dict[str, Any]:
        profile_id = envelope.payload.get("provider_profile_id")
        profile = self.repository.get_provider_profile(profile_id)
        provider = create_provider(profile)
        model_input = str(envelope.payload["model_input"])
        if envelope.kind is JobKind.PREPARE_MATERIAL:
            response = await provider.complete(
                system=str(envelope.payload["instruction"]),
                user=model_input,
                use_web_search=provider.capabilities.web_search,
            )
            return _json_object(response.content)
        if envelope.kind is JobKind.SELECT_REFERENCES:
            response = await provider.complete(
                system=str(envelope.payload["instruction"]),
                user=model_input,
            )
            return _json_object(response.content)

        response = await provider.complete(
            system=str(envelope.payload["instruction"]),
            user=model_input,
        )
        outputs = _json_object(response.content).get("outputs")
        return GenerationResult(
            outputs=outputs or [],
            raw_response=response.content,
            executor_metadata={
                "provider": response.provider,
                "model": response.model,
                "usage": response.usage,
            },
        ).model_dump()

    def _create_reference_selection_job(self, prepare_job: JobRow, result: dict[str, Any]) -> None:
        index = _reference_index(self.repository)
        payload = {
            "schema_version": 1,
            "instruction": REFERENCE_SYSTEM,
            "purified_material": result["purified_material"],
            "other_inputs": result.get("other_inputs") or "无",
            "reference_index": index,
            "result_schema": ReferenceSelectionResult.model_json_schema(),
            "model_input": _reference_user_prompt(
                self.repository.get_project(prepare_job.project_id).user_request,
                result["purified_material"],
                index,
            ),
        }
        self.repository.create_job(
            project_id=prepare_job.project_id,
            kind=JobKind.SELECT_REFERENCES,
            executor=prepare_job.executor,
            payload=payload,
        )

    def _start_experiment(
        self,
        project_id: str,
        *,
        kind: ExperimentKind,
        executor: ExecutorKind,
        rules: list[WritingRuleRow],
        provider_profile_id: str | None,
    ) -> str:
        handoff = self.repository.get_handoff(project_id, approved=True)
        fixed_input_hash = stable_hash(
            {
                "handoff_core_hash": handoff.core_hash,
                "executor": executor.value,
                "provider_profile_id": provider_profile_id,
                "output_count": 5 if kind is ExperimentKind.BATCH_FIVE else 1,
            }
        )
        experiment = self.repository.create_experiment(
            project_id=project_id,
            handoff_id=handoff.id,
            kind=kind.value,
            executor=executor.value,
            fixed_input_hash=fixed_input_hash,
            provider_profile_id=provider_profile_id,
        )
        arms = [
            self.repository.add_experiment_arm(
                experiment_id=experiment.id,
                ordinal=index,
                rule=rule,
                status="queued" if index == 0 else "waiting",
            )
            for index, rule in enumerate(rules)
        ]
        self.repository.update_experiment_status(experiment.id, ExperimentStatus.RUNNING)
        self._create_generation_job(experiment.id, arms[0].id)
        return experiment.id

    def _create_generation_job(self, experiment_id: str, arm_id: str) -> JobRow:
        experiment = self.repository.get_experiment(experiment_id)
        handoff = self.repository.get_handoff(experiment.project_id, approved=True)
        if handoff.id != experiment.handoff_id:
            raise ValueError("experiment handoff is no longer the approved revision")
        arm = self.repository.get_experiment_arm(arm_id)
        rule = self.repository.get_rule(arm.writing_rule_id)
        package = ExecutionPackage(
            handoff=self.repository.handoff_core(handoff), writing_rule=rule.body
        )
        output_count = 5 if experiment.kind == ExperimentKind.BATCH_FIVE.value else 1
        payload = {
            "schema_version": 1,
            "instruction": _generation_instruction(output_count),
            "handoff_core_hash": handoff.core_hash,
            "writing_rule_id": rule.id,
            "writing_rule_hash": rule.body_hash,
            "provider_profile_id": experiment.provider_profile_id,
            "output_count": output_count,
            "model_input": package.render(),
            "result_schema": GenerationResult.model_json_schema(),
        }
        return self.repository.create_job(
            project_id=experiment.project_id,
            kind=JobKind.GENERATE,
            executor=experiment.executor,
            payload=payload,
            handoff_id=handoff.id,
            experiment_id=experiment.id,
            experiment_arm_id=arm.id,
        )

    def _advance_experiment(self, completed_job: JobRow) -> None:
        if not completed_job.experiment_id or not completed_job.experiment_arm_id:
            return
        self.repository.update_experiment_arm_status(completed_job.experiment_arm_id, "completed")
        arms = self.repository.list_experiment_arms(completed_job.experiment_id)
        waiting = next((arm for arm in arms if arm.status == "waiting"), None)
        if waiting is None:
            self.repository.update_experiment_status(
                completed_job.experiment_id, ExperimentStatus.COMPLETED
            )
            return
        self.repository.update_experiment_arm_status(waiting.id, "queued")
        self._create_generation_job(completed_job.experiment_id, waiting.id)

    def _save_discovered_sources(self, project_id: str, items: list[dict[str, str]]) -> None:
        for item in items:
            content = item.get("content", "").strip()
            if not content:
                continue
            self.repository.add_source(
                project_id,
                kind="search",
                content=content,
                provenance={key: value for key, value in item.items() if key != "content"},
            )


def _reference_index(repository: Repository) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"cases": [], "hooks": []}
    for row in repository.list_references():
        entry = {
            "id": row.id,
            "formats": json.loads(row.formats_json),
            "techniques": json.loads(row.techniques_json),
        }
        result["cases" if row.kind == ReferenceKind.CASE.value else "hooks"].append(entry)
    return result


def _preparation_user_prompt(user_request: str, materials: list[str]) -> str:
    material_text = "\n\n".join(material.strip() for material in materials if material.strip())
    return f"用户明确要求：\n{user_request}\n\n原始材料：\n{material_text}"


def _reference_user_prompt(user_request: str, purified_material: str, index: dict[str, Any]) -> str:
    return (
        f"用户明确要求：\n{user_request}\n\n"
        f"净化材料：\n{purified_material}\n\n"
        "按写作技巧组织的参考索引：\n" + json.dumps(index, ensure_ascii=False, indent=2)
    )


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    candidate = fence.group(1) if fence else stripped
    if not candidate.startswith("{"):
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        candidate = match.group(0) if match else candidate
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("provider did not return a JSON object")
    return value


def _generation_instruction(output_count: int) -> str:
    if output_count == 5:
        output_rule = (
            "一次生成 5 篇彼此独立的完整成品，只返回合法 JSON："
            '{"outputs":["...","...","...","...","..."]}。'
        )
    else:
        output_rule = '只生成一篇完整成品，只返回合法 JSON：{"outputs":["..."]}。'
    return GENERATION_SYSTEM + "\n" + output_rule
