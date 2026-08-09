from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from inkflow.domain import HandoffStatus, stable_hash
from inkflow.storage.common import dumps, new_id, now
from inkflow.storage.database import Database
from inkflow.storage.schema import HandoffRow, ProjectRow, SourceRow


class ProjectStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, *, title: str, user_request: str) -> ProjectRow:
        if not title.strip():
            raise ValueError("project title cannot be empty")
        if not user_request.strip():
            raise ValueError("user request cannot be empty")
        stamp = now()
        row = ProjectRow(
            id=new_id("project"),
            title=title.strip(),
            user_request=user_request,
            created_at=stamp,
            updated_at=stamp,
        )
        with self.database.transaction() as session:
            session.add(row)
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
            row.updated_at = now()
            self._supersede_current_handoff(session, project_id)
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
            if session.get(ProjectRow, project_id) is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            session.add(row)
            session.execute(
                update(ProjectRow).where(ProjectRow.id == project_id).values(updated_at=now())
            )
            self._supersede_current_handoff(session, project_id)
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

    @staticmethod
    def _supersede_current_handoff(session: Any, project_id: str) -> None:
        session.execute(
            update(HandoffRow)
            .where(
                HandoffRow.project_id == project_id,
                HandoffRow.status != HandoffStatus.SUPERSEDED.value,
            )
            .values(status=HandoffStatus.SUPERSEDED.value)
        )
