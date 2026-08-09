from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from inkflow.domain import CurrentPrompt, PromptDefinition, PromptStage, stable_hash
from inkflow.prompt_entities import (
    CurrentPromptFile,
    PromptEntity,
    default_bundled_prompts,
    read_current_prompt,
    write_current_prompt,
)
from inkflow.prompting import prompt_hash, validate_prompt_template
from inkflow.storage.common import now
from inkflow.storage.database import Database
from inkflow.storage.schema import PromptRow


class PromptStore:
    """Indexes one canonical, user-editable prompt file per writing stage."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.root = database.path.parent / "prompts"
        self._syncing_current_files = False

    def ensure_bundled(self) -> None:
        self._sync_current_files()
        for stage, seed in default_bundled_prompts().items():
            row = self._index(stage)
            path = self._current_path(stage)
            if row is None or (row.origin == "bundled" and not path.is_file()):
                self._write_bundled(seed)
                continue
            if row.origin != "bundled":
                continue
            expected_document = self._document(seed)
            if row.document_hash != self._document_hash(expected_document):
                self._write_bundled(seed)

    def save(
        self,
        *,
        stage: PromptStage,
        name: str,
        system_prompt: str,
        user_template: str,
    ) -> CurrentPrompt:
        """Overwrite the canonical current file; no prompt history is created."""

        current = self.get(stage)
        validate_prompt_template(stage, system_prompt, user_template)
        if not name.strip():
            raise ValueError("prompt name cannot be empty")
        document = CurrentPromptFile(
            stage=stage,
            name=name.strip(),
            system_prompt=system_prompt,
            user_template=user_template,
        )
        write_current_prompt(self._current_path(stage), document)
        digest = prompt_hash(
            stage,
            system_prompt,
            user_template,
            contract_version=current.contract_version,
        )
        updated_at = now()
        with self.database.transaction(immediate=True) as session:
            row = session.get(PromptRow, stage.value)
            if row is None:
                raise FileNotFoundError(f"Current prompt not found for stage: {stage.value}")
            row.document_hash = self._document_hash(document)
            row.prompt_hash = digest
            row.origin = "user"
            row.updated_at = updated_at
        return self.get(stage)

    def list(self, stage: PromptStage | None = None) -> list[CurrentPrompt]:
        self._sync_current_files()
        query = select(PromptRow)
        if stage is not None:
            query = query.where(PromptRow.stage == stage.value)
        query = query.order_by(PromptRow.stage)
        with self.database.session() as session:
            rows = list(session.scalars(query))
            for row in rows:
                session.expunge(row)
        return [self._load(row) for row in rows]

    def get(self, stage: PromptStage) -> CurrentPrompt:
        self._sync_current_files()
        row = self._index(stage)
        if row is None:
            raise FileNotFoundError(f"Current prompt not found for stage: {stage.value}")
        return self._load(row)

    @staticmethod
    def definition(prompt: CurrentPrompt) -> PromptDefinition:
        return PromptDefinition(
            stage=prompt.stage,
            name=prompt.name,
            system_prompt=prompt.system_prompt,
            user_template=prompt.user_template,
            contract_version=prompt.contract_version,
            prompt_hash=prompt.prompt_hash,
        )

    def _sync_current_files(self) -> None:
        if self._syncing_current_files:
            return
        self._syncing_current_files = True
        try:
            with self.database.session() as session:
                rows = list(session.scalars(select(PromptRow)))
                for row in rows:
                    session.expunge(row)
            for row in rows:
                path = self._current_path(PromptStage(row.stage))
                if not path.exists():
                    if row.origin == "user":
                        raise RuntimeError(f"current prompt file is missing: {path}")
                    continue
                self._load(row)
        finally:
            self._syncing_current_files = False

    def _index(self, stage: PromptStage) -> PromptRow | None:
        with self.database.session() as session:
            row = session.get(PromptRow, stage.value)
            if row is not None:
                session.expunge(row)
            return row

    def _write_bundled(self, seed: PromptEntity) -> None:
        document = self._document(seed)
        path = self._current_path(seed.stage)
        write_current_prompt(path, document)
        digest = prompt_hash(
            seed.stage,
            seed.system_prompt,
            seed.user_template,
            contract_version=seed.contract_version,
        )
        updated_at = now()
        with self.database.transaction(immediate=True) as session:
            row = session.get(PromptRow, seed.stage.value)
            if row is None:
                session.add(
                    PromptRow(
                        stage=seed.stage.value,
                        current_file=self._current_relative(seed.stage),
                        contract_version=seed.contract_version,
                        document_hash=self._document_hash(document),
                        prompt_hash=digest,
                        origin="bundled",
                        updated_at=updated_at,
                    )
                )
            else:
                row.current_file = self._current_relative(seed.stage)
                row.contract_version = seed.contract_version
                row.document_hash = self._document_hash(document)
                row.prompt_hash = digest
                row.origin = "bundled"
                row.updated_at = updated_at

    def _current_path(self, stage: PromptStage) -> Path:
        return (self.root / self._current_relative(stage)).resolve()

    @staticmethod
    def _current_relative(stage: PromptStage) -> str:
        return f"current/{stage.value}.prompt.json"

    @staticmethod
    def _document(seed: PromptEntity) -> CurrentPromptFile:
        return CurrentPromptFile(
            stage=seed.stage,
            name=seed.name,
            system_prompt=seed.system_prompt,
            user_template=seed.user_template,
        )

    @staticmethod
    def _document_hash(document: CurrentPromptFile) -> str:
        return stable_hash(document.model_dump(mode="json"))

    def _load(self, row: PromptRow) -> CurrentPrompt:
        relative = Path(row.current_file)
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise RuntimeError(
                f"current prompt path escapes prompt root: {row.current_file}"
            ) from exc
        if not path.is_file():
            raise RuntimeError(f"current prompt file is missing: {path}")
        try:
            document = read_current_prompt(path)
        except (RuntimeError, ValidationError) as exc:
            raise ValueError(f"手动提示词文件无法读取：{path}；{exc}") from exc
        stage = PromptStage(row.stage)
        if document.stage is not stage:
            raise ValueError(f"手动提示词文件不能改变阶段：{path} 应为 {stage.value}")
        if not document.name.strip():
            raise ValueError(f"手动提示词文件中的名称不能为空：{path}")
        validate_prompt_template(stage, document.system_prompt, document.user_template)
        digest = prompt_hash(
            stage,
            document.system_prompt,
            document.user_template,
            contract_version=row.contract_version,
        )
        document_digest = self._document_hash(document)
        origin = row.origin
        updated_at = row.updated_at
        if document_digest != row.document_hash or digest != row.prompt_hash:
            origin = "user"
            updated_at = now()
            with self.database.transaction(immediate=True) as session:
                current = session.get(PromptRow, stage.value)
                if current is None:
                    raise FileNotFoundError(
                        f"Current prompt not found for stage: {stage.value}"
                    )
                current.document_hash = document_digest
                current.prompt_hash = digest
                current.origin = origin
                current.updated_at = updated_at
        return CurrentPrompt(
            stage=stage,
            name=document.name.strip(),
            system_prompt=document.system_prompt,
            user_template=document.user_template,
            contract_version=row.contract_version,
            prompt_hash=digest,
            current_file=row.current_file,
            current_path=str(path),
            origin=origin,
            updated_at=updated_at,
        )
