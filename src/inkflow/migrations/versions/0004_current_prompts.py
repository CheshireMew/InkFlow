"""Replace prompt revision history with one file-backed current prompt per stage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0004_current_prompts"
down_revision = "0003_prompt_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("stage", sa.String(40), primary_key=True),
        sa.Column("current_file", sa.Text(), nullable=False, unique=True),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_prompts_document_hash", "prompts", ["document_hash"])
    op.create_index("ix_prompts_prompt_hash", "prompts", ["prompt_hash"])
    op.create_index("ix_prompts_origin", "prompts", ["origin"])

    connection = op.get_bind()
    database_rows = connection.exec_driver_sql("PRAGMA database_list").fetchall()
    database_file = next(Path(row[2]) for row in database_rows if row[1] == "main")
    prompt_root = database_file.resolve().parent / "prompts"
    rows = connection.execute(
        sa.text(
            "SELECT id, stage, name, revision, system_prompt, user_template, "
            "contract_version, prompt_hash, origin, active, created_at "
            "FROM prompt_revisions ORDER BY stage, active DESC, revision DESC"
        )
    ).mappings()
    selected: dict[str, dict[str, object]] = {}
    for row in rows:
        selected.setdefault(str(row["stage"]), dict(row))

    prompt_table = sa.table(
        "prompts",
        sa.column("stage", sa.String),
        sa.column("current_file", sa.Text),
        sa.column("contract_version", sa.Integer),
        sa.column("document_hash", sa.String),
        sa.column("prompt_hash", sa.String),
        sa.column("origin", sa.String),
        sa.column("updated_at", sa.String),
    )
    for stage_value, row in selected.items():
        if stage_value not in {"prepare_material", "select_references", "generate"}:
            raise RuntimeError(f"unknown prompt stage during migration: {stage_value}")
        relative = f"current/{stage_value}.prompt.json"
        target = prompt_root / relative
        name = str(row["name"])
        system_prompt = str(row["system_prompt"])
        user_template = str(row["user_template"])
        contract_version = int(row["contract_version"])
        origin = "bundled" if row["origin"] == "bundled" else "user"

        if target.is_file():
            candidate = json.loads(target.read_text(encoding="utf-8-sig"))
            if candidate.get("stage") != stage_value:
                raise RuntimeError(f"current prompt stage differs during migration: {target}")
            candidate_name = str(candidate.get("name") or "").strip()
            candidate_system = candidate.get("system_prompt")
            candidate_template = candidate.get("user_template")
            if not candidate_name or not isinstance(candidate_system, str) or not isinstance(
                candidate_template, str
            ):
                raise RuntimeError(f"current prompt is incomplete during migration: {target}")
            if (
                candidate_name != name
                or candidate_system != system_prompt
                or candidate_template != user_template
            ):
                origin = "user"
            name = candidate_name
            system_prompt = candidate_system
            user_template = candidate_template

        payload = {
            "schema_version": 2,
            "stage": stage_value,
            "name": name,
            "system_prompt": system_prompt,
            "user_template": user_template,
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(target)
        connection.execute(
            prompt_table.insert().values(
                stage=stage_value,
                current_file=relative,
                contract_version=contract_version,
                document_hash=_stable_hash(payload),
                prompt_hash=_prompt_hash(
                    stage_value,
                    system_prompt,
                    user_template,
                    contract_version=contract_version,
                ),
                origin=origin,
                updated_at=str(row["created_at"]),
            )
        )

    with op.batch_alter_table("experiments", recreate="always") as batch:
        batch.drop_constraint("fk_experiments_prompt_revision", type_="foreignkey")
        batch.drop_column("prompt_revision_id")
    op.drop_table("prompt_revisions")
    connection.execute(sa.text("UPDATE schema_meta SET value='4' WHERE key='schema_version'"))


def downgrade() -> None:
    raise RuntimeError("the single-current-prompt migration is intentionally irreversible")


def _prompt_hash(
    stage: str,
    system_prompt: str,
    user_template: str,
    *,
    contract_version: int,
) -> str:
    return _stable_hash(
        {
            "stage": stage,
            "system_prompt": system_prompt,
            "user_template": user_template,
            "contract_version": contract_version,
        }
    )


def _stable_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
