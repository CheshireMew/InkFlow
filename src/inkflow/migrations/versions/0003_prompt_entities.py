"""Move every prompt revision to a physical immutable entity file."""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0003_prompt_entities"
down_revision = "0002_complete_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_revisions") as batch:
        batch.add_column(sa.Column("entity_file", sa.Text(), nullable=True))
        batch.add_column(sa.Column("origin", sa.String(20), nullable=True))

    connection = op.get_bind()
    database_rows = connection.exec_driver_sql("PRAGMA database_list").fetchall()
    database_file = next(Path(row[2]) for row in database_rows if row[1] == "main")
    prompt_root = database_file.resolve().parent / "prompts"
    rows = connection.execute(
        sa.text(
            "SELECT id, stage, name, revision, system_prompt, user_template, "
            "contract_version FROM prompt_revisions"
        )
    ).mappings()
    for row in rows:
        relative = f"revisions/{row['id']}.prompt.json"
        target = prompt_root / relative
        payload = {
            "schema_version": 1,
            "id": row["id"],
            "stage": row["stage"],
            "name": row["name"],
            "system_prompt": row["system_prompt"],
            "user_template": row["user_template"],
            "contract_version": row["contract_version"],
            "revision": row["revision"],
            "default_active": row["id"].startswith("prompt-builtin-"),
            "source": {"kind": "schema-2-migration"},
        }
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_text(encoding="utf-8-sig") != encoded:
            raise RuntimeError(f"existing prompt entity differs during migration: {target}")
        if not target.exists():
            target.write_text(encoded, encoding="utf-8")
        origin = "bundled" if row["id"].startswith("prompt-builtin-") else "migrated"
        connection.execute(
            sa.text(
                "UPDATE prompt_revisions SET entity_file=:entity_file, origin=:origin WHERE id=:id"
            ),
            {"entity_file": relative, "origin": origin, "id": row["id"]},
        )

    with op.batch_alter_table("prompt_revisions") as batch:
        batch.alter_column("entity_file", existing_type=sa.Text(), nullable=False)
        batch.alter_column("origin", existing_type=sa.String(20), nullable=False)
        batch.create_index("ix_prompt_revisions_origin", ["origin"])
    connection.execute(
        sa.text("UPDATE schema_meta SET value='3' WHERE key='schema_version'")
    )


def downgrade() -> None:
    # Prompt entity files and prompt history are never removed automatically.
    pass
