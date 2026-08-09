from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select, update

from inkflow.domain import ReferenceKind, stable_hash
from inkflow.storage.common import dumps, new_id, now
from inkflow.storage.database import Database
from inkflow.storage.schema import ReferenceRow, WritingRuleRow


class LibraryStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add_reference(
        self,
        *,
        reference_id: str | None,
        kind: ReferenceKind,
        title: str,
        body: str,
        formats: list[str],
        techniques: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> ReferenceRow:
        if not body.strip():
            raise ValueError("reference body cannot be empty")
        row = ReferenceRow(
            id=reference_id or new_id("reference"),
            kind=kind.value,
            title=title.strip() or "未命名参考",
            body=body.strip(),
            body_hash=stable_hash(body.strip()),
            formats_json=dumps(formats),
            techniques_json=dumps(techniques),
            active=True,
            imported_at=now(),
            metadata_json=dumps(metadata or {}),
        )
        with self.database.transaction() as session:
            if session.get(ReferenceRow, row.id) is not None:
                raise ValueError(f"reference id already exists: {row.id}")
            duplicate = session.scalar(
                select(ReferenceRow.id).where(ReferenceRow.body_hash == row.body_hash)
            )
            if duplicate:
                raise ValueError(f"reference body already exists: {duplicate}")
            session.add(row)
        return row

    def update_reference(
        self,
        reference_id: str,
        *,
        title: str,
        body: str,
        formats: list[str],
        techniques: list[str],
        active: bool,
    ) -> ReferenceRow:
        if not body.strip():
            raise ValueError("reference body cannot be empty")
        body_hash = stable_hash(body.strip())
        with self.database.transaction() as session:
            row = session.get(ReferenceRow, reference_id)
            if row is None:
                raise FileNotFoundError(f"Reference not found: {reference_id}")
            duplicate = session.scalar(
                select(ReferenceRow.id).where(
                    ReferenceRow.body_hash == body_hash, ReferenceRow.id != reference_id
                )
            )
            if duplicate:
                raise ValueError(f"reference body already exists: {duplicate}")
            row.title = title.strip() or "未命名参考"
            row.body = body.strip()
            row.body_hash = body_hash
            row.formats_json = dumps(formats)
            row.techniques_json = dumps(techniques)
            row.active = active
            session.flush()
            session.expunge(row)
            return row

    def list_references(
        self, *, kind: ReferenceKind | None = None, include_inactive: bool = False
    ) -> list[ReferenceRow]:
        query = select(ReferenceRow)
        if kind:
            query = query.where(ReferenceRow.kind == kind.value)
        if not include_inactive:
            query = query.where(ReferenceRow.active.is_(True))
        query = query.order_by(ReferenceRow.kind, ReferenceRow.title, ReferenceRow.id)
        with self.database.session() as session:
            rows = list(session.scalars(query))
            for row in rows:
                session.expunge(row)
            return rows

    def get_reference(self, reference_id: str) -> ReferenceRow:
        with self.database.session() as session:
            row = session.get(ReferenceRow, reference_id)
            if row is None:
                raise FileNotFoundError(f"Reference not found: {reference_id}")
            session.expunge(row)
            return row

    def get_references(self, reference_ids: Iterable[str]) -> list[ReferenceRow]:
        ids = list(dict.fromkeys(reference_ids))
        if not ids:
            return []
        with self.database.session() as session:
            rows = list(session.scalars(select(ReferenceRow).where(ReferenceRow.id.in_(ids))))
            by_id = {row.id: row for row in rows}
            missing = [item for item in ids if item not in by_id]
            if missing:
                raise FileNotFoundError(f"References not found: {', '.join(missing)}")
            ordered = [by_id[item] for item in ids]
            for row in ordered:
                session.expunge(row)
            return ordered

    def find_reference(self, reference_id: str) -> ReferenceRow | None:
        with self.database.session() as session:
            row = session.get(ReferenceRow, reference_id)
            if row is not None:
                session.expunge(row)
            return row

    def add_rule(self, *, name: str, body: str, activate: bool = False) -> WritingRuleRow:
        if not name.strip() or not body.strip():
            raise ValueError("writing rule name and body cannot be empty")
        with self.database.transaction() as session:
            revision = session.scalar(
                select(func.max(WritingRuleRow.revision)).where(WritingRuleRow.name == name.strip())
            )
            if activate:
                session.execute(update(WritingRuleRow).values(active=False))
            row = WritingRuleRow(
                id=new_id("rule"),
                name=name.strip(),
                revision=int(revision or 0) + 1,
                body=body.strip(),
                body_hash=stable_hash(body.strip()),
                active=activate,
                created_at=now(),
            )
            session.add(row)
        return row

    def list_rules(self) -> list[WritingRuleRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(WritingRuleRow).order_by(
                        WritingRuleRow.created_at.desc(), WritingRuleRow.id
                    )
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def get_rule(self, rule_id: str | None = None) -> WritingRuleRow:
        with self.database.session() as session:
            row = (
                session.get(WritingRuleRow, rule_id)
                if rule_id
                else session.scalar(select(WritingRuleRow).where(WritingRuleRow.active.is_(True)))
            )
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
        with self.database.transaction() as session:
            row = session.get(WritingRuleRow, rule_id)
            if row is None:
                raise FileNotFoundError(f"Writing rule not found: {rule_id}")
            session.execute(update(WritingRuleRow).values(active=False))
            row.active = True
            session.flush()
            session.expunge(row)
            return row
