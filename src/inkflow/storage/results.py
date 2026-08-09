from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, func, select, update

from inkflow.domain import ReviewState
from inkflow.storage.common import new_id, now
from inkflow.storage.database import Database
from inkflow.storage.schema import (
    ExperimentRow,
    GenerationRevisionRow,
    GenerationRow,
    WritingRuleRow,
)


@dataclass(frozen=True)
class ResultContext:
    generation: GenerationRow
    latest_revision: GenerationRevisionRow | None
    writing_rule: WritingRuleRow
    experiment: ExperimentRow


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
                        case(
                            (GenerationRow.review_state == ReviewState.ACCEPTED.value, 0),
                            (GenerationRow.review_state == ReviewState.UNREVIEWED.value, 1),
                            else_=2,
                        ),
                        ExperimentRow.created_at.desc(),
                        GenerationRow.created_at,
                        GenerationRow.output_index,
                    )
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def list_with_context(
        self, project_id: str, *, experiment_id: str | None = None
    ) -> list[ResultContext]:
        latest_revisions = (
            select(
                GenerationRevisionRow.generation_id.label("generation_id"),
                func.max(GenerationRevisionRow.revision).label("revision"),
            )
            .group_by(GenerationRevisionRow.generation_id)
            .subquery()
        )
        query = (
            select(
                GenerationRow,
                GenerationRevisionRow,
                WritingRuleRow,
                ExperimentRow,
            )
            .join(WritingRuleRow, GenerationRow.writing_rule_id == WritingRuleRow.id)
            .join(ExperimentRow, GenerationRow.experiment_id == ExperimentRow.id)
            .outerjoin(
                latest_revisions,
                latest_revisions.c.generation_id == GenerationRow.id,
            )
            .outerjoin(
                GenerationRevisionRow,
                (GenerationRevisionRow.generation_id == GenerationRow.id)
                & (GenerationRevisionRow.revision == latest_revisions.c.revision),
            )
            .where(GenerationRow.project_id == project_id)
        )
        if experiment_id is not None:
            query = query.where(GenerationRow.experiment_id == experiment_id)
        query = query.order_by(
            case(
                (GenerationRow.review_state == ReviewState.ACCEPTED.value, 0),
                (GenerationRow.review_state == ReviewState.UNREVIEWED.value, 1),
                else_=2,
            ),
            ExperimentRow.created_at.desc(),
            GenerationRow.created_at,
            GenerationRow.output_index,
        )
        with self.database.session() as session:
            result: list[ResultContext] = []
            for generation, revision, rule, experiment in session.execute(query):
                result.append(
                    ResultContext(
                        generation=generation,
                        latest_revision=revision,
                        writing_rule=rule,
                        experiment=experiment,
                    )
                )
            return result

    def get(self, generation_id: str) -> GenerationRow:
        with self.database.session() as session:
            row = session.get(GenerationRow, generation_id)
            if row is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            session.expunge(row)
            return row

    def review(self, generation_id: str, state: ReviewState) -> GenerationRow:
        with self.database.transaction() as session:
            row = session.get(GenerationRow, generation_id)
            if row is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            if state is ReviewState.ACCEPTED:
                session.execute(
                    update(GenerationRow)
                    .where(
                        GenerationRow.project_id == row.project_id,
                        GenerationRow.review_state == ReviewState.ACCEPTED.value,
                    )
                    .values(review_state=ReviewState.UNREVIEWED.value)
                )
            row.review_state = state.value
            session.flush()
            session.expunge(row)
            return row

    def add_revision(self, generation_id: str, content: str) -> GenerationRevisionRow:
        if not content.strip():
            raise ValueError("edited result cannot be empty")
        with self.database.transaction() as session:
            generation = session.get(GenerationRow, generation_id)
            if generation is None:
                raise FileNotFoundError(f"Generation not found: {generation_id}")
            generation.review_state = ReviewState.UNREVIEWED.value
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
