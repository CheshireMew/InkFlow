from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select, update

from inkflow.domain import (
    ExperimentStatus,
    HandoffCore,
    HandoffStatus,
    JobEnvelope,
    JobKind,
    JobStatus,
    ReferenceKind,
    stable_hash,
)
from inkflow.storage.database import Database
from inkflow.storage.schema import (
    ExperimentArmRow,
    ExperimentRow,
    GenerationRow,
    HandoffRow,
    JobRow,
    ProjectRow,
    ProviderProfileRow,
    ReferenceRow,
    SourceRow,
    WritingRuleRow,
)


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_project(self, *, title: str, user_request: str) -> ProjectRow:
        now = _now()
        row = ProjectRow(
            id=_id("project"),
            title=title.strip() or "未命名写作项目",
            user_request=user_request.strip(),
            created_at=now,
            updated_at=now,
        )
        if not row.user_request:
            raise ValueError("user_request cannot be empty")
        with self.database.session() as session:
            session.add(row)
            session.commit()
        return row

    def get_project(self, project_id: str) -> ProjectRow:
        with self.database.session() as session:
            row = session.get(ProjectRow, project_id)
            if row is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            session.expunge(row)
            return row

    def list_projects(self) -> list[ProjectRow]:
        with self.database.session() as session:
            rows = list(session.scalars(select(ProjectRow).order_by(ProjectRow.updated_at.desc())))
            for row in rows:
                session.expunge(row)
            return rows

    def add_source(
        self,
        project_id: str,
        *,
        kind: str,
        content: str,
        provenance: dict[str, Any] | None = None,
    ) -> SourceRow:
        project = self.get_project(project_id)
        body = content.strip()
        if not body:
            raise ValueError("source content cannot be empty")
        row = SourceRow(
            id=_id("source"),
            project_id=project.id,
            kind=kind,
            content=body,
            content_hash=stable_hash(body),
            provenance_json=_json(provenance or {}),
            created_at=_now(),
        )
        with self.database.session() as session:
            session.add(row)
            session.execute(
                update(ProjectRow).where(ProjectRow.id == project.id).values(updated_at=_now())
            )
            session.commit()
        return row

    def list_sources(self, project_id: str) -> list[SourceRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(SourceRow)
                    .where(SourceRow.project_id == project_id)
                    .order_by(SourceRow.created_at)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def add_reference(
        self,
        *,
        reference_id: str,
        kind: ReferenceKind,
        title: str,
        body: str,
        formats: Iterable[str],
        techniques: Iterable[str],
        metadata: dict[str, Any] | None = None,
    ) -> ReferenceRow:
        normalized_body = body.strip()
        if not normalized_body:
            raise ValueError("reference body cannot be empty")
        body_hash = stable_hash(normalized_body)
        row = ReferenceRow(
            id=reference_id,
            kind=kind.value,
            title=title.strip() or "未命名参考",
            body=normalized_body,
            body_hash=body_hash,
            formats_json=_json(list(dict.fromkeys(formats))),
            techniques_json=_json(list(dict.fromkeys(techniques))),
            active=True,
            imported_at=_now(),
            metadata_json=_json(metadata or {}),
        )
        with self.database.session() as session:
            duplicate = session.scalar(
                select(ReferenceRow).where(ReferenceRow.body_hash == body_hash)
            )
            if duplicate is not None:
                if duplicate.id == reference_id:
                    session.expunge(duplicate)
                    return duplicate
                raise ValueError(f"reference body duplicates {duplicate.id}")
            existing = session.get(ReferenceRow, reference_id)
            if existing is not None:
                raise ValueError(f"reference id already exists: {reference_id}")
            session.add(row)
            session.commit()
        return row

    def list_references(
        self,
        *,
        kind: ReferenceKind | None = None,
        active_only: bool = True,
    ) -> list[ReferenceRow]:
        query = select(ReferenceRow)
        if kind is not None:
            query = query.where(ReferenceRow.kind == kind.value)
        if active_only:
            query = query.where(ReferenceRow.active.is_(True))
        query = query.order_by(ReferenceRow.kind, ReferenceRow.id)
        with self.database.session() as session:
            rows = list(session.scalars(query))
            for row in rows:
                session.expunge(row)
            return rows

    def get_references(self, reference_ids: Iterable[str]) -> list[ReferenceRow]:
        ids = list(dict.fromkeys(reference_ids))
        if not ids:
            return []
        with self.database.session() as session:
            found = {
                row.id: row
                for row in session.scalars(select(ReferenceRow).where(ReferenceRow.id.in_(ids)))
            }
            missing = [reference_id for reference_id in ids if reference_id not in found]
            if missing:
                raise FileNotFoundError("References not found: " + ", ".join(missing))
            rows = [found[reference_id] for reference_id in ids]
            for row in rows:
                session.expunge(row)
            return rows

    def find_reference(self, reference_id: str) -> ReferenceRow | None:
        with self.database.session() as session:
            row = session.get(ReferenceRow, reference_id)
            if row is not None:
                session.expunge(row)
            return row

    def add_rule(self, *, name: str, body: str, activate: bool = False) -> WritingRuleRow:
        normalized_name = name.strip()
        normalized_body = body.strip()
        if not normalized_name or not normalized_body:
            raise ValueError("rule name and body cannot be empty")
        with self.database.session() as session:
            latest = session.scalar(
                select(func.max(WritingRuleRow.revision)).where(
                    WritingRuleRow.name == normalized_name
                )
            )
            if activate:
                session.execute(update(WritingRuleRow).values(active=False))
            row = WritingRuleRow(
                id=_id("rule"),
                name=normalized_name,
                revision=int(latest or 0) + 1,
                body=normalized_body,
                body_hash=stable_hash(normalized_body),
                active=activate,
                created_at=_now(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def list_rules(self) -> list[WritingRuleRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(WritingRuleRow).order_by(
                        WritingRuleRow.created_at.desc(), WritingRuleRow.id.desc()
                    )
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def get_rule(self, rule_id: str | None = None) -> WritingRuleRow:
        with self.database.session() as session:
            if rule_id:
                row = session.get(WritingRuleRow, rule_id)
            else:
                row = session.scalar(select(WritingRuleRow).where(WritingRuleRow.active.is_(True)))
            if row is None:
                raise FileNotFoundError("Writing rule not found")
            session.expunge(row)
            return row

    def find_rule_by_body_hash(self, body_hash: str) -> WritingRuleRow | None:
        with self.database.session() as session:
            row = session.scalar(
                select(WritingRuleRow).where(WritingRuleRow.body_hash == body_hash)
            )
            if row is not None:
                session.expunge(row)
            return row

    def activate_rule(self, rule_id: str) -> WritingRuleRow:
        with self.database.session() as session:
            row = session.get(WritingRuleRow, rule_id)
            if row is None:
                raise FileNotFoundError(f"Writing rule not found: {rule_id}")
            session.execute(update(WritingRuleRow).values(active=False))
            row.active = True
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def create_handoff(
        self,
        project_id: str,
        *,
        purified_material: str,
        case_ids: list[str],
        hook_ids: list[str],
        other_inputs: str = "无",
    ) -> HandoffRow:
        project = self.get_project(project_id)
        cases = self.get_references(case_ids)
        hooks = self.get_references(hook_ids)
        if any(row.kind != ReferenceKind.CASE.value for row in cases):
            raise ValueError("case_ids can only contain case references")
        if any(row.kind != ReferenceKind.HOOK.value for row in hooks):
            raise ValueError("hook_ids can only contain hook references")
        if {row.body_hash for row in cases} & {row.body_hash for row in hooks}:
            raise ValueError("a reference cannot serve as both case and hook")
        core = HandoffCore(
            user_request=project.user_request,
            purified_material=purified_material.strip(),
            reference_cases=[row.body for row in cases],
            reference_hooks=[row.body for row in hooks],
            other_inputs=other_inputs.strip() or "无",
        )
        if not core.purified_material:
            raise ValueError("purified_material cannot be empty")
        with self.database.session() as session:
            latest = session.scalar(
                select(func.max(HandoffRow.revision)).where(HandoffRow.project_id == project_id)
            )
            session.execute(
                update(HandoffRow)
                .where(
                    HandoffRow.project_id == project_id,
                    HandoffRow.status != HandoffStatus.SUPERSEDED.value,
                )
                .values(status=HandoffStatus.SUPERSEDED.value)
            )
            row = HandoffRow(
                id=_id("handoff"),
                project_id=project_id,
                revision=int(latest or 0) + 1,
                status=HandoffStatus.DRAFT.value,
                user_request=core.user_request,
                purified_material=core.purified_material,
                reference_case_ids_json=_json(case_ids),
                reference_hook_ids_json=_json(hook_ids),
                reference_cases_json=_json(core.reference_cases),
                reference_hooks_json=_json(core.reference_hooks),
                other_inputs=core.other_inputs,
                core_hash=core.content_hash(),
                created_at=_now(),
                approved_at=None,
            )
            session.add(row)
            session.execute(
                update(ProjectRow).where(ProjectRow.id == project_id).values(updated_at=_now())
            )
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def get_handoff(self, project_id: str, *, approved: bool = False) -> HandoffRow:
        query = select(HandoffRow).where(HandoffRow.project_id == project_id)
        if approved:
            query = query.where(HandoffRow.status == HandoffStatus.APPROVED.value)
        else:
            query = query.where(HandoffRow.status != HandoffStatus.SUPERSEDED.value)
        query = query.order_by(HandoffRow.revision.desc())
        with self.database.session() as session:
            row = session.scalar(query)
            if row is None:
                raise FileNotFoundError(f"Handoff not found for project: {project_id}")
            session.expunge(row)
            return row

    def approve_handoff(self, project_id: str) -> HandoffRow:
        with self.database.session() as session:
            row = session.scalar(
                select(HandoffRow)
                .where(
                    HandoffRow.project_id == project_id,
                    HandoffRow.status == HandoffStatus.DRAFT.value,
                )
                .order_by(HandoffRow.revision.desc())
            )
            if row is None:
                raise FileNotFoundError(f"Draft handoff not found for project: {project_id}")
            row.status = HandoffStatus.APPROVED.value
            row.approved_at = _now()
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def handoff_core(self, row: HandoffRow) -> HandoffCore:
        return HandoffCore(
            user_request=row.user_request,
            purified_material=row.purified_material,
            reference_cases=_loads(row.reference_cases_json, []),
            reference_hooks=_loads(row.reference_hooks_json, []),
            other_inputs=row.other_inputs,
        )

    def create_job(
        self,
        *,
        project_id: str,
        kind: JobKind,
        executor: str,
        payload: dict[str, Any],
        handoff_id: str | None = None,
        experiment_id: str | None = None,
        experiment_arm_id: str | None = None,
        status: JobStatus = JobStatus.PENDING,
    ) -> JobRow:
        row = JobRow(
            id=_id("job"),
            project_id=project_id,
            handoff_id=handoff_id,
            experiment_id=experiment_id,
            experiment_arm_id=experiment_arm_id,
            kind=kind.value,
            executor=executor,
            status=status.value,
            payload_json=_json(payload),
            input_hash=stable_hash(payload),
            lease_token=None,
            leased_at=None,
            attempt=0,
            result_json=None,
            error=None,
            created_at=_now(),
            completed_at=None,
        )
        with self.database.session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def lease_next_job(
        self,
        project_id: str | None = None,
        *,
        executor: str | None = None,
    ) -> JobEnvelope | None:
        with self.database.session() as session:
            query = select(JobRow).where(JobRow.status == JobStatus.PENDING.value)
            if project_id:
                query = query.where(JobRow.project_id == project_id)
            if executor:
                query = query.where(JobRow.executor == executor)
            row = session.scalar(query.order_by(JobRow.created_at).limit(1))
            if row is None:
                return None
            token = secrets.token_urlsafe(24)
            row.status = JobStatus.LEASED.value
            row.lease_token = token
            row.leased_at = _now()
            row.attempt += 1
            session.commit()
            return JobEnvelope(
                job_id=row.id,
                lease_token=token,
                kind=JobKind(row.kind),
                input_hash=row.input_hash,
                payload=_loads(row.payload_json, {}),
            )

    def get_job(self, job_id: str) -> JobRow:
        with self.database.session() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                raise FileNotFoundError(f"Job not found: {job_id}")
            session.expunge(row)
            return row

    def list_jobs(self, project_id: str) -> list[JobRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(JobRow)
                    .where(JobRow.project_id == project_id)
                    .order_by(JobRow.created_at, JobRow.id)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def complete_job(
        self, job_id: str, *, lease_token: str | None, result: dict[str, Any]
    ) -> JobRow:
        with self.database.session() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                raise FileNotFoundError(f"Job not found: {job_id}")
            if row.executor == "external" and row.lease_token != lease_token:
                raise PermissionError("lease token does not match")
            if row.status not in {JobStatus.LEASED.value, JobStatus.PENDING.value}:
                raise ValueError(f"job is not completable from status {row.status}")
            row.status = JobStatus.SUCCEEDED.value
            row.result_json = _json(result)
            row.completed_at = _now()
            row.error = None
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def fail_job(self, job_id: str, *, error: str, retry: bool = False) -> JobRow:
        with self.database.session() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                raise FileNotFoundError(f"Job not found: {job_id}")
            row.status = JobStatus.PENDING.value if retry else JobStatus.FAILED.value
            row.error = error
            row.lease_token = None
            row.leased_at = None
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def create_experiment(
        self,
        *,
        project_id: str,
        handoff_id: str,
        kind: str,
        executor: str,
        fixed_input_hash: str,
        provider_profile_id: str | None,
    ) -> ExperimentRow:
        row = ExperimentRow(
            id=_id("experiment"),
            project_id=project_id,
            handoff_id=handoff_id,
            kind=kind,
            executor=executor,
            provider_profile_id=provider_profile_id,
            fixed_input_hash=fixed_input_hash,
            status=ExperimentStatus.QUEUED.value,
            created_at=_now(),
            completed_at=None,
        )
        with self.database.session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def add_experiment_arm(
        self,
        *,
        experiment_id: str,
        ordinal: int,
        rule: WritingRuleRow,
        status: str,
    ) -> ExperimentArmRow:
        row = ExperimentArmRow(
            id=_id("arm"),
            experiment_id=experiment_id,
            ordinal=ordinal,
            writing_rule_id=rule.id,
            writing_rule_hash=rule.body_hash,
            status=status,
        )
        with self.database.session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def get_experiment(self, experiment_id: str) -> ExperimentRow:
        with self.database.session() as session:
            row = session.get(ExperimentRow, experiment_id)
            if row is None:
                raise FileNotFoundError(f"Experiment not found: {experiment_id}")
            session.expunge(row)
            return row

    def list_experiments(self, project_id: str) -> list[ExperimentRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(ExperimentRow)
                    .where(ExperimentRow.project_id == project_id)
                    .order_by(ExperimentRow.created_at.desc())
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def list_experiment_arms(self, experiment_id: str) -> list[ExperimentArmRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(ExperimentArmRow)
                    .where(ExperimentArmRow.experiment_id == experiment_id)
                    .order_by(ExperimentArmRow.ordinal)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def get_experiment_arm(self, arm_id: str) -> ExperimentArmRow:
        with self.database.session() as session:
            row = session.get(ExperimentArmRow, arm_id)
            if row is None:
                raise FileNotFoundError(f"Experiment arm not found: {arm_id}")
            session.expunge(row)
            return row

    def update_experiment_arm_status(self, arm_id: str, status: str) -> None:
        with self.database.session() as session:
            row = session.get(ExperimentArmRow, arm_id)
            if row is None:
                raise FileNotFoundError(f"Experiment arm not found: {arm_id}")
            row.status = status
            session.commit()

    def update_experiment_status(self, experiment_id: str, status: ExperimentStatus) -> None:
        with self.database.session() as session:
            row = session.get(ExperimentRow, experiment_id)
            if row is None:
                raise FileNotFoundError(f"Experiment not found: {experiment_id}")
            row.status = status.value
            row.completed_at = (
                _now() if status in {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED} else None
            )
            session.commit()

    def save_generations(
        self,
        *,
        job: JobRow,
        handoff_id: str,
        writing_rule_id: str,
        outputs: list[str],
        raw_response: str | None,
        executor_metadata: dict[str, Any],
    ) -> list[GenerationRow]:
        rows: list[GenerationRow] = []
        for index, content in enumerate(outputs):
            if not content.strip():
                continue
            rows.append(
                GenerationRow(
                    id=_id("generation"),
                    project_id=job.project_id,
                    job_id=job.id,
                    handoff_id=handoff_id,
                    experiment_id=job.experiment_id,
                    writing_rule_id=writing_rule_id,
                    output_index=index,
                    content=content.strip(),
                    raw_response=raw_response,
                    executor_metadata_json=_json(executor_metadata),
                    selected=False,
                    created_at=_now(),
                )
            )
        if not rows:
            raise ValueError("generation outputs cannot be empty")
        with self.database.session() as session:
            session.add_all(rows)
            session.commit()
            for row in rows:
                session.refresh(row)
                session.expunge(row)
        return rows

    def list_generations(self, project_id: str) -> list[GenerationRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(GenerationRow)
                    .where(GenerationRow.project_id == project_id)
                    .order_by(GenerationRow.created_at, GenerationRow.output_index)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def select_generation(self, generation_id: str) -> GenerationRow:
        with self.database.session() as session:
            row = session.get(GenerationRow, generation_id)
            if row is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            session.execute(
                update(GenerationRow)
                .where(GenerationRow.project_id == row.project_id)
                .values(selected=False)
            )
            row.selected = True
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def get_generation(self, generation_id: str) -> GenerationRow:
        with self.database.session() as session:
            row = session.get(GenerationRow, generation_id)
            if row is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            session.expunge(row)
            return row

    def save_provider_profile(
        self,
        *,
        name: str,
        adapter: str,
        base_url: str,
        model: str,
        capabilities: dict[str, Any],
        parameters: dict[str, Any],
        secret_key_name: str,
        activate: bool,
    ) -> ProviderProfileRow:
        with self.database.session() as session:
            if activate:
                session.execute(update(ProviderProfileRow).values(active=False))
            existing = session.scalar(
                select(ProviderProfileRow).where(ProviderProfileRow.name == name)
            )
            if existing is None:
                row = ProviderProfileRow(
                    id=_id("provider"),
                    name=name,
                    adapter=adapter,
                    base_url=base_url,
                    model=model,
                    capabilities_json=_json(capabilities),
                    parameters_json=_json(parameters),
                    secret_key_name=secret_key_name,
                    active=activate,
                    created_at=_now(),
                )
                session.add(row)
            else:
                row = existing
                row.adapter = adapter
                row.base_url = base_url
                row.model = model
                row.capabilities_json = _json(capabilities)
                row.parameters_json = _json(parameters)
                row.secret_key_name = secret_key_name
                row.active = activate
            session.commit()
            session.refresh(row)
            session.expunge(row)
            return row

    def get_provider_profile(self, profile_id: str | None = None) -> ProviderProfileRow:
        with self.database.session() as session:
            row = (
                session.get(ProviderProfileRow, profile_id)
                if profile_id
                else session.scalar(
                    select(ProviderProfileRow).where(ProviderProfileRow.active.is_(True))
                )
            )
            if row is None:
                raise FileNotFoundError("Provider profile not found")
            session.expunge(row)
            return row


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)
