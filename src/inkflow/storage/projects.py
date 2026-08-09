from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update

from inkflow.domain import HandoffStatus, JobKind, JobStatus, stable_hash
from inkflow.storage.common import dumps, new_id, now
from inkflow.storage.database import Database
from inkflow.storage.schema import HandoffRow, JobAttemptRow, JobRow, ProjectRow, SourceRow


@dataclass(frozen=True)
class ProjectInputSnapshot:
    project: ProjectRow
    sources: list[SourceRow]


class ProjectStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, *, title: str, user_request: str) -> ProjectRow:
        return self.create_with_sources(title=title, user_request=user_request, sources=[])

    def create_with_sources(
        self,
        *,
        title: str,
        user_request: str,
        sources: list[tuple[str, str, dict[str, Any]]],
    ) -> ProjectRow:
        if not title.strip():
            raise ValueError("project title cannot be empty")
        if not user_request.strip():
            raise ValueError("user request cannot be empty")
        if any(not content.strip() for _kind, content, _provenance in sources):
            raise ValueError("source content cannot be empty")
        stamp = now()
        row = ProjectRow(
            id=new_id("project"),
            title=title.strip(),
            user_request=user_request,
            input_revision=1,
            created_at=stamp,
            updated_at=stamp,
        )
        with self.database.transaction() as session:
            session.add(row)
            for kind, content, provenance in sources:
                session.add(
                    SourceRow(
                        id=new_id("source"),
                        project_id=row.id,
                        kind=kind,
                        content=content,
                        content_hash=stable_hash(content),
                        provenance_json=dumps(provenance),
                        created_at=stamp,
                    )
                )
        return row

    def get(self, project_id: str) -> ProjectRow:
        with self.database.session() as session:
            row = session.get(ProjectRow, project_id)
            if row is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            session.expunge(row)
            return row

    def list(self) -> list[ProjectRow]:
        with self.database.session() as session:
            rows = list(session.scalars(select(ProjectRow).order_by(ProjectRow.updated_at.desc())))
            for row in rows:
                session.expunge(row)
            return rows

    def update_request(self, project_id: str, user_request: str) -> ProjectRow:
        if not user_request.strip():
            raise ValueError("user request cannot be empty")
        with self.database.transaction() as session:
            row = session.get(ProjectRow, project_id)
            if row is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            if row.user_request == user_request:
                session.expunge(row)
                return row
            row.user_request = user_request
            row.input_revision += 1
            row.updated_at = now()
            self._invalidate_current_input(session, project_id)
            session.flush()
            session.expunge(row)
            return row

    def add_source(
        self,
        project_id: str,
        *,
        kind: str,
        content: str,
        provenance: dict[str, Any],
    ) -> SourceRow:
        if not content.strip():
            raise ValueError("source content cannot be empty")
        row = SourceRow(
            id=new_id("source"),
            project_id=project_id,
            kind=kind,
            content=content,
            content_hash=stable_hash(content),
            provenance_json=dumps(provenance),
            created_at=now(),
        )
        with self.database.transaction() as session:
            project = session.get(ProjectRow, project_id)
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            session.add(row)
            project.input_revision += 1
            project.updated_at = now()
            self._invalidate_current_input(session, project_id)
        return row

    def update_source(self, project_id: str, source_id: str, content: str) -> SourceRow:
        if not content.strip():
            raise ValueError("source content cannot be empty")
        with self.database.transaction() as session:
            project = session.get(ProjectRow, project_id)
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            row = session.get(SourceRow, source_id)
            if row is None or row.project_id != project_id:
                raise FileNotFoundError(f"Source not found: {source_id}")
            if row.content == content:
                session.expunge(row)
                return row
            row.content = content
            row.content_hash = stable_hash(content)
            project.input_revision += 1
            project.updated_at = now()
            self._invalidate_current_input(session, project_id)
            session.flush()
            session.expunge(row)
            return row

    def list_sources(self, project_id: str) -> list[SourceRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(SourceRow)
                    .where(SourceRow.project_id == project_id)
                    .order_by(SourceRow.created_at, SourceRow.id)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def input_snapshot(self, project_id: str) -> ProjectInputSnapshot:
        with self.database.session() as session:
            project = session.get(ProjectRow, project_id)
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            sources = list(
                session.scalars(
                    select(SourceRow)
                    .where(SourceRow.project_id == project_id)
                    .order_by(SourceRow.created_at, SourceRow.id)
                )
            )
            session.expunge(project)
            for source in sources:
                session.expunge(source)
            return ProjectInputSnapshot(project=project, sources=sources)

    @staticmethod
    def _invalidate_current_input(session: Any, project_id: str) -> None:
        session.execute(
            update(HandoffRow)
            .where(
                HandoffRow.project_id == project_id,
                HandoffRow.status != HandoffStatus.SUPERSEDED.value,
            )
            .values(status=HandoffStatus.SUPERSEDED.value)
        )
        active_statuses = {
            JobStatus.WAITING.value,
            JobStatus.BLOCKED.value,
            JobStatus.PENDING.value,
            JobStatus.LEASED.value,
        }
        active_job_ids = select(JobRow.id).where(
            JobRow.project_id == project_id,
            JobRow.kind.in_(
                [JobKind.PREPARE_MATERIAL.value, JobKind.SELECT_REFERENCES.value]
            ),
            JobRow.status.in_(active_statuses),
        )
        stamp = now()
        session.execute(
            update(JobAttemptRow)
            .where(
                JobAttemptRow.job_id.in_(active_job_ids),
                JobAttemptRow.status == JobStatus.LEASED.value,
            )
            .values(
                status=JobStatus.SUPERSEDED.value,
                error="project input changed while this attempt was active",
                completed_at=stamp,
            )
        )
        session.execute(
            update(JobRow)
            .where(JobRow.id.in_(active_job_ids))
            .values(status=JobStatus.SUPERSEDED.value)
        )
