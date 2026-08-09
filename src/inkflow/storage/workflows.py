from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

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
from inkflow.storage.common import dumps, loads, new_id, now
from inkflow.storage.database import Database
from inkflow.storage.schema import (
    ExperimentArmRow,
    ExperimentRow,
    GenerationRow,
    HandoffRow,
    JobAttemptRow,
    JobRow,
    ProjectRow,
    ReferenceRow,
    SourceRow,
    WritingRuleRow,
)


@dataclass(frozen=True)
class ExperimentJobSpec:
    rule: WritingRuleRow
    payload: dict[str, Any]


class StaleProjectInput(ValueError):
    pass


class WorkflowStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_preparation_job(
        self,
        *,
        project_id: str,
        executor: str,
        payload: dict[str, Any],
        expected_input_revision: int,
    ) -> JobRow:
        row = self._new_job(
            project_id=project_id,
            kind=JobKind.PREPARE_MATERIAL,
            executor=executor,
            payload=payload,
            status=JobStatus.PENDING,
            handoff_id=None,
            experiment_id=None,
            experiment_arm_id=None,
        )
        with self.database.transaction(immediate=True) as session:
            project = session.get(ProjectRow, project_id)
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            if project.input_revision != expected_input_revision:
                raise StaleProjectInput(
                    "project input changed before the preparation job was created"
                )
            active = session.scalar(
                select(func.count(JobRow.id)).where(
                    JobRow.project_id == project_id,
                    JobRow.kind.in_(
                        [JobKind.PREPARE_MATERIAL.value, JobKind.SELECT_REFERENCES.value]
                    ),
                    JobRow.status.in_(
                        [
                            JobStatus.PENDING.value,
                            JobStatus.LEASED.value,
                            JobStatus.WAITING.value,
                            JobStatus.BLOCKED.value,
                        ]
                    ),
                )
            )
            if int(active or 0):
                raise ValueError("project already has an active preparation chain")
            session.add(row)
        return row

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

    def list_attempts(self, job_id: str) -> list[JobAttemptRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(JobAttemptRow)
                    .where(JobAttemptRow.job_id == job_id)
                    .order_by(JobAttemptRow.attempt)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def lease_next_job(
        self, project_id: str | None = None, *, executor: str | None = None
    ) -> JobEnvelope | None:
        with self.database.transaction(immediate=True) as session:
            query = select(JobRow).where(JobRow.status == JobStatus.PENDING.value)
            if project_id:
                query = query.where(JobRow.project_id == project_id)
            if executor:
                query = query.where(JobRow.executor == executor)
            row = session.scalar(query.order_by(JobRow.created_at, JobRow.id).limit(1))
            if row is None:
                return None
            attempt_number = (
                int(
                    session.scalar(
                        select(func.max(JobAttemptRow.attempt)).where(
                            JobAttemptRow.job_id == row.id
                        )
                    )
                    or 0
                )
                + 1
            )
            token = secrets.token_urlsafe(24)
            attempt = JobAttemptRow(
                id=new_id("attempt"),
                job_id=row.id,
                attempt=attempt_number,
                status=JobStatus.LEASED.value,
                lease_token=token,
                leased_at=now(),
                result_json=None,
                raw_response=None,
                format_error=None,
                error=None,
                completed_at=None,
            )
            row.status = JobStatus.LEASED.value
            session.add(attempt)
            session.flush()
            return JobEnvelope(
                job_id=row.id,
                attempt_id=attempt.id,
                attempt=attempt_number,
                lease_token=token,
                kind=JobKind(row.kind),
                input_hash=row.input_hash,
                payload=loads(row.payload_json, {}),
            )

    def complete_preparation(
        self,
        *,
        job_id: str,
        attempt_id: str,
        lease_token: str,
        result: dict[str, Any],
        raw_response: str | None,
        next_payload: dict[str, Any],
    ) -> JobRow:
        stale = False
        next_job: JobRow | None = None
        with self.database.transaction() as session:
            job, attempt = self._leased(session, job_id, attempt_id, lease_token)
            payload = loads(job.payload_json, {})
            stale = not self._input_revision_is_current(session, job, attempt, payload)
            if not stale:
                self._succeed(job, attempt, result, raw_response)
                for item in result.get("discovered_sources", []):
                    content = str(item["content"])
                    session.add(
                        SourceRow(
                            id=new_id("source"),
                            project_id=job.project_id,
                            kind="search",
                            content=content,
                            content_hash=stable_hash(content),
                            provenance_json=dumps(
                                {
                                    "title": item["title"],
                                    "url": item["url"],
                                    "use": item["use"],
                                }
                            ),
                            created_at=now(),
                        )
                    )
                next_job = self._new_job(
                    project_id=job.project_id,
                    kind=JobKind.SELECT_REFERENCES,
                    executor=job.executor,
                    payload=next_payload,
                    status=JobStatus.PENDING,
                )
                session.add(next_job)
                session.flush()
                session.expunge(next_job)
        if stale:
            raise StaleProjectInput("project input changed; preparation was superseded")
        assert next_job is not None
        return next_job

    def complete_selection(
        self,
        *,
        job_id: str,
        attempt_id: str,
        lease_token: str,
        result: dict[str, Any],
        raw_response: str | None,
    ) -> HandoffRow:
        stale = False
        handoff: HandoffRow | None = None
        with self.database.transaction() as session:
            job, attempt = self._leased(session, job_id, attempt_id, lease_token)
            payload = loads(job.payload_json, {})
            stale = not self._input_revision_is_current(session, job, attempt, payload)
            if not stale:
                case_ids = list(result["case_ids"])
                hook_ids = list(result["hook_ids"])
                cases = self._ordered_references(session, case_ids)
                hooks = self._ordered_references(session, hook_ids)
                self._validate_reference_kinds(cases, hooks)
                input_snapshot = payload["project_input"]
                core = HandoffCore(
                    user_request=str(input_snapshot["user_request"]),
                    purified_material=payload["purified_material"],
                    reference_cases=[row.body for row in cases],
                    reference_hooks=[row.body for row in hooks],
                    other_inputs=payload.get("other_inputs") or "无",
                )
                self._succeed(job, attempt, result, raw_response)
                handoff = self._insert_handoff(
                    session,
                    project_id=job.project_id,
                    project_input_revision=int(input_snapshot["revision"]),
                    core=core,
                    case_ids=case_ids,
                    hook_ids=hook_ids,
                )
                session.flush()
                session.expunge(handoff)
        if stale:
            raise StaleProjectInput("project input changed; selection was superseded")
        assert handoff is not None
        return handoff

    def create_handoff_revision(
        self,
        *,
        project_id: str,
        core: HandoffCore,
        case_ids: list[str],
        hook_ids: list[str],
    ) -> HandoffRow:
        with self.database.transaction() as session:
            project = session.get(ProjectRow, project_id)
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            if core.user_request != project.user_request:
                raise ValueError("handoff user request must equal the current project request")
            handoff = self._insert_handoff(
                session,
                project_id=project_id,
                project_input_revision=project.input_revision,
                core=core,
                case_ids=case_ids,
                hook_ids=hook_ids,
            )
            session.flush()
            session.expunge(handoff)
            return handoff

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

    def list_handoffs(self, project_id: str) -> list[HandoffRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(HandoffRow)
                    .where(HandoffRow.project_id == project_id)
                    .order_by(HandoffRow.revision.desc())
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def approve_handoff(self, project_id: str) -> HandoffRow:
        with self.database.transaction() as session:
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
            project = session.get(ProjectRow, project_id)
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            if row.project_input_revision != project.input_revision:
                row.status = HandoffStatus.SUPERSEDED.value
                raise ValueError("handoff was built from an older project input revision")
            row.status = HandoffStatus.APPROVED.value
            row.approved_at = now()
            session.flush()
            session.expunge(row)
            return row

    @staticmethod
    def handoff_core(row: HandoffRow) -> HandoffCore:
        return HandoffCore(
            user_request=row.user_request,
            purified_material=row.purified_material,
            reference_cases=loads(row.reference_cases_json, []),
            reference_hooks=loads(row.reference_hooks_json, []),
            other_inputs=row.other_inputs,
        )

    def create_experiment(
        self,
        *,
        project_id: str,
        handoff_id: str,
        kind: str,
        executor: str,
        provider_profile_id: str | None,
        prompt_snapshot: dict[str, Any],
        provider_snapshot: dict[str, Any],
        generation_settings: dict[str, Any],
        input_package_hash: str,
        jobs: list[ExperimentJobSpec],
    ) -> ExperimentRow:
        if not jobs:
            raise ValueError("experiment requires at least one arm")
        experiment = ExperimentRow(
            id=new_id("experiment"),
            project_id=project_id,
            handoff_id=handoff_id,
            kind=kind,
            executor=executor,
            provider_profile_id=provider_profile_id,
            prompt_snapshot_json=dumps(prompt_snapshot),
            provider_snapshot_json=dumps(provider_snapshot),
            generation_settings_json=dumps(generation_settings),
            input_package_hash=input_package_hash,
            status=ExperimentStatus.RUNNING.value,
            created_at=now(),
            completed_at=None,
        )
        with self.database.transaction() as session:
            project = session.get(ProjectRow, project_id)
            handoff = session.get(HandoffRow, handoff_id)
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            if handoff is None or handoff.project_id != project_id:
                raise FileNotFoundError(f"Handoff not found: {handoff_id}")
            if (
                handoff.status != HandoffStatus.APPROVED.value
                or handoff.project_input_revision != project.input_revision
            ):
                raise ValueError("experiment requires the approved current project input")
            session.add(experiment)
            session.flush()
            for ordinal, spec in enumerate(jobs):
                arm = ExperimentArmRow(
                    id=new_id("arm"),
                    experiment_id=experiment.id,
                    ordinal=ordinal,
                    writing_rule_id=spec.rule.id,
                    writing_rule_hash=spec.rule.body_hash,
                    status="queued" if ordinal == 0 else "waiting",
                )
                session.add(arm)
                session.flush()
                session.add(
                    self._new_job(
                        project_id=project_id,
                        kind=JobKind.GENERATE,
                        executor=executor,
                        payload=spec.payload,
                        status=JobStatus.PENDING if ordinal == 0 else JobStatus.WAITING,
                        handoff_id=handoff_id,
                        experiment_id=experiment.id,
                        experiment_arm_id=arm.id,
                    )
                )
        return experiment

    def complete_generation(
        self,
        *,
        job_id: str,
        attempt_id: str,
        lease_token: str,
        outputs: list[str],
        raw_response: str | None,
        executor_metadata: dict[str, Any],
    ) -> list[GenerationRow]:
        with self.database.transaction() as session:
            job, attempt = self._leased(session, job_id, attempt_id, lease_token)
            payload = loads(job.payload_json, {})
            result = {
                "outputs": outputs,
                "raw_response": raw_response,
                "executor_metadata": executor_metadata,
            }
            self._succeed(job, attempt, result, raw_response)
            rows = [
                GenerationRow(
                    id=new_id("generation"),
                    project_id=job.project_id,
                    job_id=job.id,
                    handoff_id=str(job.handoff_id),
                    experiment_id=job.experiment_id,
                    writing_rule_id=payload["writing_rule_id"],
                    output_index=index,
                    content=content,
                    raw_response=raw_response,
                    executor_metadata_json=dumps(executor_metadata),
                    prompt_snapshot_json=dumps(payload["prompt_snapshot"]),
                    provider_snapshot_json=dumps(payload.get("provider_snapshot") or {}),
                    generation_settings_json=dumps(payload["generation_settings"]),
                    review_state="unreviewed",
                    created_at=now(),
                )
                for index, content in enumerate(outputs)
            ]
            session.add_all(rows)
            if job.experiment_arm_id:
                arm = session.get(ExperimentArmRow, job.experiment_arm_id)
                if arm:
                    arm.status = "completed"
            if job.experiment_id:
                next_job = session.scalar(
                    select(JobRow)
                    .join(ExperimentArmRow, JobRow.experiment_arm_id == ExperimentArmRow.id)
                    .where(
                        JobRow.experiment_id == job.experiment_id,
                        JobRow.status == JobStatus.WAITING.value,
                    )
                    .order_by(ExperimentArmRow.ordinal)
                    .limit(1)
                )
                if next_job:
                    next_job.status = JobStatus.PENDING.value
                    next_arm = session.get(ExperimentArmRow, next_job.experiment_arm_id)
                    if next_arm:
                        next_arm.status = "queued"
                else:
                    experiment = session.get(ExperimentRow, job.experiment_id)
                    if experiment:
                        experiment.status = ExperimentStatus.COMPLETED.value
                        experiment.completed_at = now()
            session.flush()
            for row in rows:
                session.expunge(row)
            return rows

    def fail_attempt(
        self,
        *,
        job_id: str,
        attempt_id: str,
        lease_token: str,
        error: str,
        raw_response: str | None = None,
        format_error: str | None = None,
    ) -> JobRow:
        with self.database.transaction() as session:
            job, attempt = self._leased(session, job_id, attempt_id, lease_token)
            attempt.status = JobStatus.FAILED.value
            attempt.error = error
            attempt.raw_response = raw_response
            attempt.format_error = format_error
            attempt.completed_at = now()
            job.status = JobStatus.FAILED.value
            if job.experiment_arm_id:
                arm = session.get(ExperimentArmRow, job.experiment_arm_id)
                if arm:
                    arm.status = "failed"
            if job.experiment_id:
                experiment = session.get(ExperimentRow, job.experiment_id)
                if experiment:
                    experiment.status = ExperimentStatus.FAILED.value
                    experiment.completed_at = now()
                blocked_jobs = list(
                    session.scalars(
                        select(JobRow).where(
                            JobRow.experiment_id == job.experiment_id,
                            JobRow.status == JobStatus.WAITING.value,
                        )
                    )
                )
                for blocked_job in blocked_jobs:
                    blocked_job.status = JobStatus.BLOCKED.value
                    if blocked_job.experiment_arm_id:
                        blocked_arm = session.get(
                            ExperimentArmRow, blocked_job.experiment_arm_id
                        )
                        if blocked_arm:
                            blocked_arm.status = "blocked"
            session.flush()
            session.expunge(job)
            return job

    def retry_job(self, job_id: str) -> JobRow:
        with self.database.transaction() as session:
            job = session.get(JobRow, job_id)
            if job is None:
                raise FileNotFoundError(f"Job not found: {job_id}")
            if job.status not in {JobStatus.FAILED.value, JobStatus.LEASED.value}:
                raise ValueError("only a failed or leased job can be retried")
            if job.status == JobStatus.LEASED.value:
                attempt = session.scalar(
                    select(JobAttemptRow)
                    .where(
                        JobAttemptRow.job_id == job.id,
                        JobAttemptRow.status == JobStatus.LEASED.value,
                    )
                    .order_by(JobAttemptRow.attempt.desc())
                )
                if attempt:
                    attempt.status = JobStatus.FAILED.value
                    attempt.error = "attempt was explicitly released for retry"
                    attempt.completed_at = now()
            job.status = JobStatus.PENDING.value
            if job.experiment_arm_id:
                arm = session.get(ExperimentArmRow, job.experiment_arm_id)
                if arm:
                    arm.status = "queued"
            if job.experiment_id:
                experiment = session.get(ExperimentRow, job.experiment_id)
                if experiment:
                    experiment.status = ExperimentStatus.RUNNING.value
                    experiment.completed_at = None
                blocked_jobs = list(
                    session.scalars(
                        select(JobRow).where(
                            JobRow.experiment_id == job.experiment_id,
                            JobRow.status == JobStatus.BLOCKED.value,
                        )
                    )
                )
                for blocked_job in blocked_jobs:
                    blocked_job.status = JobStatus.WAITING.value
                    if blocked_job.experiment_arm_id:
                        blocked_arm = session.get(
                            ExperimentArmRow, blocked_job.experiment_arm_id
                        )
                        if blocked_arm:
                            blocked_arm.status = "waiting"
            session.flush()
            session.expunge(job)
            return job

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

    def project_activity(self, project_id: str) -> dict[str, Any]:
        with self.database.session() as session:
            if session.get(ProjectRow, project_id) is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            jobs = list(
                session.execute(
                    select(JobRow.id, JobRow.status)
                    .where(JobRow.project_id == project_id)
                    .order_by(JobRow.created_at, JobRow.id)
                )
            )
            experiments = list(
                session.execute(
                    select(ExperimentRow.id, ExperimentRow.status)
                    .where(ExperimentRow.project_id == project_id)
                    .order_by(ExperimentRow.created_at, ExperimentRow.id)
                )
            )
        state = {
            "jobs": [[job_id, status] for job_id, status in jobs],
            "experiments": [
                [experiment_id, status] for experiment_id, status in experiments
            ],
        }
        active = any(
            status in {JobStatus.PENDING.value, JobStatus.LEASED.value}
            for _job_id, status in jobs
        )
        return {"active": active, "state_token": stable_hash(state)}

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

    def _insert_handoff(
        self,
        session: Session,
        *,
        project_id: str,
        project_input_revision: int,
        core: HandoffCore,
        case_ids: list[str],
        hook_ids: list[str],
    ) -> HandoffRow:
        if not core.purified_material.strip():
            raise ValueError("purified material cannot be empty")
        revision = session.scalar(
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
            id=new_id("handoff"),
            project_id=project_id,
            revision=int(revision or 0) + 1,
            project_input_revision=project_input_revision,
            status=HandoffStatus.DRAFT.value,
            user_request=core.user_request,
            purified_material=core.purified_material,
            reference_case_ids_json=dumps(case_ids),
            reference_hook_ids_json=dumps(hook_ids),
            reference_cases_json=dumps(core.reference_cases),
            reference_hooks_json=dumps(core.reference_hooks),
            other_inputs=core.other_inputs or "无",
            core_hash=core.content_hash(),
            created_at=now(),
            approved_at=None,
        )
        session.add(row)
        session.execute(
            update(ProjectRow).where(ProjectRow.id == project_id).values(updated_at=now())
        )
        return row

    @staticmethod
    def _input_revision_is_current(
        session: Session,
        job: JobRow,
        attempt: JobAttemptRow,
        payload: dict[str, Any],
    ) -> bool:
        project = session.get(ProjectRow, job.project_id)
        expected = int((payload.get("project_input") or {}).get("revision") or 0)
        if project is not None and expected > 0 and project.input_revision == expected:
            return True
        job.status = JobStatus.SUPERSEDED.value
        attempt.status = JobStatus.SUPERSEDED.value
        attempt.error = "project input changed while this attempt was active"
        attempt.completed_at = now()
        return False

    @staticmethod
    def _ordered_references(session: Session, ids: list[str]) -> list[ReferenceRow]:
        if not ids:
            return []
        rows = list(session.scalars(select(ReferenceRow).where(ReferenceRow.id.in_(ids))))
        by_id = {row.id: row for row in rows}
        missing = [item for item in ids if item not in by_id]
        if missing:
            raise FileNotFoundError(f"References not found: {', '.join(missing)}")
        return [by_id[item] for item in ids]

    @staticmethod
    def _validate_reference_kinds(cases: list[ReferenceRow], hooks: list[ReferenceRow]) -> None:
        if any(row.kind != ReferenceKind.CASE.value for row in cases):
            raise ValueError("case_ids can only contain case references")
        if any(row.kind != ReferenceKind.HOOK.value for row in hooks):
            raise ValueError("hook_ids can only contain hook references")
        if {row.body_hash for row in cases} & {row.body_hash for row in hooks}:
            raise ValueError("a reference cannot serve as both case and hook")

    @staticmethod
    def _new_job(
        *,
        project_id: str,
        kind: JobKind,
        executor: str,
        payload: dict[str, Any],
        status: JobStatus,
        handoff_id: str | None = None,
        experiment_id: str | None = None,
        experiment_arm_id: str | None = None,
    ) -> JobRow:
        return JobRow(
            id=new_id("job"),
            project_id=project_id,
            handoff_id=handoff_id,
            experiment_id=experiment_id,
            experiment_arm_id=experiment_arm_id,
            kind=kind.value,
            executor=executor,
            status=status.value,
            payload_json=dumps(payload),
            input_hash=stable_hash(payload),
            created_at=now(),
        )

    @staticmethod
    def _leased(
        session: Session, job_id: str, attempt_id: str, lease_token: str
    ) -> tuple[JobRow, JobAttemptRow]:
        job = session.get(JobRow, job_id)
        if job is None:
            raise FileNotFoundError(f"Job not found: {job_id}")
        attempt = session.get(JobAttemptRow, attempt_id)
        if attempt is None or attempt.job_id != job_id:
            raise PermissionError("attempt does not belong to the job")
        if attempt.lease_token != lease_token:
            raise PermissionError("lease token does not match")
        if job.status != JobStatus.LEASED.value or attempt.status != JobStatus.LEASED.value:
            raise ValueError("job attempt is no longer completable")
        return job, attempt

    @staticmethod
    def _succeed(
        job: JobRow,
        attempt: JobAttemptRow,
        result: dict[str, Any],
        raw_response: str | None,
    ) -> None:
        job.status = JobStatus.SUCCEEDED.value
        attempt.status = JobStatus.SUCCEEDED.value
        attempt.result_json = dumps(result)
        attempt.raw_response = raw_response
        attempt.error = None
        attempt.format_error = None
        attempt.completed_at = now()
