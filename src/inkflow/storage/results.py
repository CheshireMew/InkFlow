from __future__ import annotations

from sqlalchemy import func, select, update

from inkflow.storage.common import new_id, now
from inkflow.storage.database import Database
from inkflow.storage.schema import ExperimentRow, GenerationRevisionRow, GenerationRow


class ResultStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self, project_id: str) -> list[GenerationRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(GenerationRow)
                    .join(ExperimentRow, GenerationRow.experiment_id == ExperimentRow.id)
                    .where(GenerationRow.project_id == project_id)
                    .order_by(
                        GenerationRow.selected.desc(),
                        ExperimentRow.created_at.desc(),
                        GenerationRow.created_at,
                        GenerationRow.output_index,
                    )
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def get(self, generation_id: str) -> GenerationRow:
        with self.database.session() as session:
            row = session.get(GenerationRow, generation_id)
            if row is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            session.expunge(row)
            return row

    def select(self, generation_id: str) -> GenerationRow:
        with self.database.transaction() as session:
            row = session.get(GenerationRow, generation_id)
            if row is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            session.execute(
                update(GenerationRow)
                .where(GenerationRow.project_id == row.project_id)
                .values(selected=False)
            )
            row.selected = True
            session.flush()
            session.expunge(row)
            return row

    def add_revision(self, generation_id: str, content: str) -> GenerationRevisionRow:
        if not content.strip():
            raise ValueError("edited result cannot be empty")
        with self.database.transaction() as session:
            if session.get(GenerationRow, generation_id) is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            revision = session.scalar(
                select(func.max(GenerationRevisionRow.revision)).where(
                    GenerationRevisionRow.generation_id == generation_id
                )
            )
            row = GenerationRevisionRow(
                id=new_id("result-revision"),
                generation_id=generation_id,
                revision=int(revision or 0) + 1,
                content=content,
                origin="user",
                created_at=now(),
            )
            session.add(row)
        return row

    def list_revisions(self, generation_id: str) -> list[GenerationRevisionRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(GenerationRevisionRow)
                    .where(GenerationRevisionRow.generation_id == generation_id)
                    .order_by(GenerationRevisionRow.revision)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def current_content(self, generation_id: str) -> str:
        with self.database.session() as session:
            generation = session.get(GenerationRow, generation_id)
            if generation is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            revision = session.scalar(
                select(GenerationRevisionRow)
                .where(GenerationRevisionRow.generation_id == generation_id)
                .order_by(GenerationRevisionRow.revision.desc())
            )
            return revision.content if revision else generation.content
