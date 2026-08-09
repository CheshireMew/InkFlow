from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, select, update

from inkflow.domain import PromptDefinition, PromptStage
from inkflow.prompt_entities import (
    PromptEntity,
    bundled_prompt_entities,
    read_prompt_entity,
    write_editable_prompt,
    write_prompt_entity,
)
from inkflow.prompting import prompt_hash, validate_prompt_template
from inkflow.storage.common import new_id, now
from inkflow.storage.database import Database
from inkflow.storage.schema import PromptRevisionRow

LEGACY_DEFAULT_IDS = {
    "prompt-default-prepare-material",
    "prompt-default-select-references",
    "prompt-default-generate",
}


class PromptStore:
    """Indexes immutable prompt entity files and never changes their content in place."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.root = database.path.parent / "prompts"
        self._syncing_manual_edits = False

    def ensure_bundled(self) -> None:
        self._sync_manual_edits()
        bundled = bundled_prompt_entities()
        defaults = {entity.stage: entity.id for _path, entity in bundled if entity.default_active}
        with self.database.session() as session:
            active_rows = list(
                session.scalars(select(PromptRevisionRow).where(PromptRevisionRow.active.is_(True)))
            )
            for row in active_rows:
                session.expunge(row)
        active_before = {PromptStage(row.stage): row for row in active_rows}

        for _source_path, entity in bundled:
            self._ensure_bundled_entity(entity)

        for stage, default_id in defaults.items():
            active_row = active_before.get(stage)
            should_follow_bundled_default = (
                active_row is not None
                and active_row.origin == "bundled"
                and self._read_entity(active_row).default_active
            )
            if (
                active_row is None
                or active_row.id == default_id
                or active_row.id in LEGACY_DEFAULT_IDS
                or should_follow_bundled_default
            ):
                self._activate_bundled_default(default_id)
        self._refresh_editable_files()

    def add(
        self,
        *,
        stage: PromptStage,
        name: str,
        system_prompt: str,
        user_template: str,
        activate: bool = False,
    ) -> PromptRevisionRow:
        """Create a user-authorized prompt revision and its physical entity file."""

        self._sync_manual_edits()
        row = self._create_revision(
            stage=stage,
            name=name,
            system_prompt=system_prompt,
            user_template=user_template,
            activate=activate,
            source={"kind": "user"},
        )
        if activate:
            self._refresh_editable_files(stage)
        return row

    def list(self, stage: PromptStage | None = None) -> list[PromptRevisionRow]:
        self._sync_manual_edits()
        query = select(PromptRevisionRow)
        if stage:
            query = query.where(PromptRevisionRow.stage == stage.value)
        query = query.order_by(PromptRevisionRow.stage, PromptRevisionRow.revision.desc())
        with self.database.session() as session:
            rows = list(session.scalars(query))
            for row in rows:
                session.expunge(row)
        return [self._verified(row) for row in rows]

    def get(
        self, prompt_id: str | None = None, *, stage: PromptStage | None = None
    ) -> PromptRevisionRow:
        self._sync_manual_edits()
        with self.database.session() as session:
            if prompt_id:
                row = session.get(PromptRevisionRow, prompt_id)
            elif stage:
                row = session.scalar(
                    select(PromptRevisionRow).where(
                        PromptRevisionRow.stage == stage.value,
                        PromptRevisionRow.active.is_(True),
                    )
                )
            else:
                raise ValueError("prompt_id or stage is required")
            if row is None:
                raise FileNotFoundError("Prompt revision not found")
            if stage and row.stage != stage.value:
                raise ValueError(f"prompt revision does not belong to stage {stage.value}")
            session.expunge(row)
        return self._verified(row)

    def activate(self, prompt_id: str) -> PromptRevisionRow:
        self._sync_manual_edits()
        with self.database.transaction() as session:
            row = session.get(PromptRevisionRow, prompt_id)
            if row is None:
                raise FileNotFoundError(f"Prompt revision not found: {prompt_id}")
            self._verified(row)
            session.execute(
                update(PromptRevisionRow)
                .where(PromptRevisionRow.stage == row.stage)
                .values(active=False)
            )
            row.active = True
            session.flush()
            session.expunge(row)
        self._refresh_editable_files(PromptStage(row.stage))
        return row

    def entity_path(self, row: PromptRevisionRow) -> str:
        return str((self.root / row.entity_file).resolve())

    def editable_file(self, row: PromptRevisionRow) -> str | None:
        if not row.active:
            return None
        return str(self._editable_path(PromptStage(row.stage)))

    def definition(self, row: PromptRevisionRow) -> PromptDefinition:
        entity = self._read_entity(row)
        return PromptDefinition(
            id=row.id,
            stage=PromptStage(row.stage),
            name=row.name,
            revision=row.revision,
            system_prompt=entity.system_prompt,
            user_template=entity.user_template,
            contract_version=row.contract_version,
            prompt_hash=row.prompt_hash,
            entity_file=str((self.root / row.entity_file).resolve()),
        )

    def _ensure_bundled_entity(self, seed: PromptEntity) -> None:
        expected_hash = prompt_hash(seed.stage, seed.system_prompt, seed.user_template)
        with self.database.session() as session:
            existing = session.get(PromptRevisionRow, seed.id)
            if existing is not None:
                session.expunge(existing)
        if existing is not None:
            if existing.prompt_hash != expected_hash:
                raise RuntimeError(
                    f"bundled prompt id changed content instead of creating a new id: {seed.id}"
                )
            self._verified(existing)
            return

        with self.database.transaction(immediate=True) as session:
            revision = (
                int(
                    session.scalar(
                        select(func.max(PromptRevisionRow.revision)).where(
                            PromptRevisionRow.stage == seed.stage.value
                        )
                    )
                    or 0
                )
                + 1
            )
            entity_file = f"revisions/{seed.id}.prompt.json"
            entity = seed.model_copy(update={"revision": revision})
            write_prompt_entity(self.root / entity_file, entity)
            session.add(
                PromptRevisionRow(
                    id=seed.id,
                    stage=seed.stage.value,
                    name=seed.name,
                    revision=revision,
                    system_prompt=seed.system_prompt,
                    user_template=seed.user_template,
                    contract_version=seed.contract_version,
                    prompt_hash=expected_hash,
                    entity_file=entity_file,
                    origin="bundled",
                    active=False,
                    created_at=now(),
                )
            )

    def _create_revision(
        self,
        *,
        stage: PromptStage,
        name: str,
        system_prompt: str,
        user_template: str,
        activate: bool,
        source: dict[str, str],
    ) -> PromptRevisionRow:
        validate_prompt_template(stage, system_prompt, user_template)
        if not name.strip():
            raise ValueError("prompt name cannot be empty")
        with self.database.transaction(immediate=True) as session:
            revision = (
                int(
                    session.scalar(
                        select(func.max(PromptRevisionRow.revision)).where(
                            PromptRevisionRow.stage == stage.value
                        )
                    )
                    or 0
                )
                + 1
            )
            prompt_id = new_id("prompt")
            entity_file = f"revisions/{prompt_id}.prompt.json"
            entity = PromptEntity(
                id=prompt_id,
                stage=stage,
                name=name.strip(),
                revision=revision,
                system_prompt=system_prompt,
                user_template=user_template,
                source=source,
            )
            write_prompt_entity(self.root / entity_file, entity)
            if activate:
                session.execute(
                    update(PromptRevisionRow)
                    .where(PromptRevisionRow.stage == stage.value)
                    .values(active=False)
                )
            row = PromptRevisionRow(
                id=prompt_id,
                stage=stage.value,
                name=entity.name,
                revision=revision,
                system_prompt=system_prompt,
                user_template=user_template,
                contract_version=entity.contract_version,
                prompt_hash=prompt_hash(stage, system_prompt, user_template),
                entity_file=entity_file,
                origin="user",
                active=activate,
                created_at=now(),
            )
            session.add(row)
        return self._verified(row)

    def _sync_manual_edits(self) -> None:
        if self._syncing_manual_edits:
            return
        self._syncing_manual_edits = True
        try:
            with self.database.session() as session:
                rows = list(
                    session.scalars(
                        select(PromptRevisionRow).where(PromptRevisionRow.active.is_(True))
                    )
                )
                for row in rows:
                    session.expunge(row)
            for row in rows:
                indexed = self._read_entity(row)
                path = self._editable_path(PromptStage(row.stage))
                if not path.exists():
                    write_editable_prompt(path, indexed)
                    continue
                try:
                    candidate = read_prompt_entity(path)
                except (RuntimeError, ValidationError) as exc:
                    raise ValueError(f"手动提示词文件无法读取：{path}；{exc}") from exc
                if candidate.stage.value != row.stage:
                    raise ValueError(f"手动提示词文件不能改变阶段：{path} 应为 {row.stage}")
                if candidate.contract_version != row.contract_version:
                    raise ValueError(f"手动提示词文件不能改变格式合同版本：{path}")
                validate_prompt_template(
                    candidate.stage, candidate.system_prompt, candidate.user_template
                )
                changed = (
                    candidate.name.strip() != row.name
                    or candidate.system_prompt != row.system_prompt
                    or candidate.user_template != row.user_template
                )
                if changed:
                    revised = self._create_revision(
                        stage=PromptStage(row.stage),
                        name=candidate.name,
                        system_prompt=candidate.system_prompt,
                        user_template=candidate.user_template,
                        activate=True,
                        source={
                            "kind": "user-manual-file-edit",
                            "editable_file": str(path),
                        },
                    )
                    write_editable_prompt(path, self._read_entity(revised))
                else:
                    write_editable_prompt(path, indexed)
        finally:
            self._syncing_manual_edits = False

    def _refresh_editable_files(self, stage: PromptStage | None = None) -> None:
        query = select(PromptRevisionRow).where(PromptRevisionRow.active.is_(True))
        if stage is not None:
            query = query.where(PromptRevisionRow.stage == stage.value)
        with self.database.session() as session:
            rows = list(session.scalars(query))
            for row in rows:
                session.expunge(row)
        for row in rows:
            entity = self._read_entity(row)
            write_editable_prompt(self._editable_path(PromptStage(row.stage)), entity)

    def _editable_path(self, stage: PromptStage) -> Path:
        return (self.root / "current" / f"{stage.value}.prompt.json").resolve()

    def _activate_bundled_default(self, prompt_id: str) -> None:
        with self.database.transaction() as session:
            row = session.get(PromptRevisionRow, prompt_id)
            if row is None:
                raise RuntimeError(f"bundled default prompt was not indexed: {prompt_id}")
            session.execute(
                update(PromptRevisionRow)
                .where(PromptRevisionRow.stage == row.stage)
                .values(active=False)
            )
            row.active = True

    def _verified(self, row: PromptRevisionRow) -> PromptRevisionRow:
        self._read_entity(row)
        return row

    def _read_entity(self, row: PromptRevisionRow) -> PromptEntity:
        relative = Path(row.entity_file)
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise RuntimeError(
                f"prompt entity path escapes prompt root: {row.entity_file}"
            ) from exc
        if not path.is_file():
            raise RuntimeError(f"prompt entity file is missing: {path}")
        entity = read_prompt_entity(path)
        expected = {
            "id": row.id,
            "stage": row.stage,
            "name": row.name,
            "revision": row.revision,
            "system_prompt": row.system_prompt,
            "user_template": row.user_template,
            "contract_version": row.contract_version,
        }
        actual = {
            "id": entity.id,
            "stage": entity.stage.value,
            "name": entity.name,
            "revision": entity.revision,
            "system_prompt": entity.system_prompt,
            "user_template": entity.user_template,
            "contract_version": entity.contract_version,
        }
        if actual != expected:
            raise RuntimeError(
                f"prompt entity file differs from immutable database index: {path}; "
                "save the edit as a new prompt revision"
            )
        if prompt_hash(entity.stage, entity.system_prompt, entity.user_template) != row.prompt_hash:
            raise RuntimeError(f"prompt entity hash mismatch: {path}")
        return entity
