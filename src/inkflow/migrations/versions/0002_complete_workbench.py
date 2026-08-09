"""Add prompt revisions, immutable runtime snapshots, attempts and result revisions."""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from inkflow.domain import PromptStage, stable_hash
from inkflow.prompt_entities import default_bundled_prompts
from inkflow.prompting import prompt_hash

revision = "0002_complete_workbench"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

BUNDLED_PROMPTS = default_bundled_prompts()
DEFAULT_PROMPT_IDS = {stage: prompt.id for stage, prompt in BUNDLED_PROMPTS.items()}


def upgrade() -> None:
    _create_and_seed_prompts()
    _upgrade_provider_profiles()
    _upgrade_experiments()
    _create_attempts_and_upgrade_jobs()
    _upgrade_generations()
    op.create_table(
        "schema_meta",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )
    op.execute(sa.text("INSERT INTO schema_meta (key, value) VALUES ('schema_version', '2')"))


def _create_and_seed_prompts() -> None:
    table = op.create_table(
        "prompt_revisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("stage", "revision", name="uq_prompt_stage_revision"),
    )
    op.create_index("ix_prompt_revisions_stage", "prompt_revisions", ["stage"])
    op.create_index("ix_prompt_revisions_prompt_hash", "prompt_revisions", ["prompt_hash"])
    op.create_index("ix_prompt_revisions_active", "prompt_revisions", ["active"])
    rows = []
    for stage, default in BUNDLED_PROMPTS.items():
        rows.append(
            {
                "id": DEFAULT_PROMPT_IDS[stage],
                "stage": stage.value,
                "name": default.name,
                "revision": 1,
                "system_prompt": default.system_prompt,
                "user_template": default.user_template,
                "contract_version": default.contract_version,
                "prompt_hash": prompt_hash(stage, default.system_prompt, default.user_template),
                "active": True,
                "created_at": "2026-08-08T00:00:00.000+00:00",
            }
        )
    op.bulk_insert(table, rows)


def _upgrade_provider_profiles() -> None:
    naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table(
        "provider_profiles", naming_convention=naming, recreate="always"
    ) as batch:
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("config_hash", sa.String(64), nullable=False, server_default=""))
        batch.drop_constraint("uq_provider_profiles_name", type_="unique")
        batch.create_unique_constraint("uq_provider_name_revision", ["name", "revision"])
        batch.create_index("ix_provider_profiles_name", ["name"])
        batch.create_index("ix_provider_profiles_config_hash", ["config_hash"])
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, name, revision, adapter, base_url, model, capabilities_json, "
            "parameters_json FROM provider_profiles"
        )
    ).mappings()
    for row in rows:
        config_hash = stable_hash(
            {
                "name": row["name"],
                "revision": row["revision"],
                "adapter": row["adapter"],
                "base_url": row["base_url"],
                "model": row["model"],
                "capabilities": json.loads(row["capabilities_json"] or "{}"),
                "parameters": json.loads(row["parameters_json"] or "{}"),
            }
        )
        connection.execute(
            sa.text("UPDATE provider_profiles SET config_hash=:value WHERE id=:id"),
            {"value": config_hash, "id": row["id"]},
        )


def _upgrade_experiments() -> None:
    default_id = DEFAULT_PROMPT_IDS[PromptStage.GENERATE]
    with op.batch_alter_table("experiments") as batch:
        batch.add_column(
            sa.Column(
                "prompt_revision_id",
                sa.String(64),
                nullable=False,
                server_default=default_id,
            )
        )
        batch.create_foreign_key(
            "fk_experiments_prompt_revision",
            "prompt_revisions",
            ["prompt_revision_id"],
            ["id"],
        )
        batch.add_column(
            sa.Column("prompt_snapshot_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("provider_snapshot_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("generation_settings_json", sa.Text(), nullable=False, server_default="{}")
        )


def _create_attempts_and_upgrade_jobs() -> None:
    op.create_table(
        "job_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id", ondelete="CASCADE")),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("lease_token", sa.String(96), nullable=False, unique=True),
        sa.Column("leased_at", sa.String(40), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.Column("raw_response", sa.Text()),
        sa.Column("format_error", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("completed_at", sa.String(40)),
        sa.UniqueConstraint("job_id", "attempt", name="uq_job_attempt"),
    )
    op.create_index("ix_job_attempts_job_id", "job_attempts", ["job_id"])
    op.create_index("ix_job_attempts_status", "job_attempts", ["status"])
    connection = op.get_bind()
    old_rows = connection.execute(
        sa.text(
            "SELECT id, status, lease_token, leased_at, attempt, result_json, error, "
            "created_at, completed_at FROM jobs WHERE attempt > 0 OR status IN "
            "('leased', 'succeeded', 'failed')"
        )
    ).mappings()
    for row in old_rows:
        connection.execute(
            sa.text(
                "INSERT INTO job_attempts "
                "(id, job_id, attempt, status, lease_token, leased_at, result_json, raw_response, "
                "format_error, error, completed_at) VALUES "
                "(:id, :job_id, :attempt, :status, :lease_token, :leased_at, :result_json, NULL, "
                "NULL, :error, :completed_at)"
            ),
            {
                "id": f"attempt-migrated-{row['id']}",
                "job_id": row["id"],
                "attempt": max(int(row["attempt"] or 0), 1),
                "status": row["status"],
                "lease_token": row["lease_token"] or f"migrated-{row['id']}",
                "leased_at": row["leased_at"] or row["created_at"],
                "result_json": row["result_json"],
                "error": row["error"],
                "completed_at": row["completed_at"],
            },
        )
    with op.batch_alter_table("jobs", recreate="always") as batch:
        batch.drop_column("lease_token")
        batch.drop_column("leased_at")
        batch.drop_column("attempt")
        batch.drop_column("result_json")
        batch.drop_column("error")
        batch.drop_column("completed_at")


def _upgrade_generations() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.add_column(
            sa.Column("prompt_snapshot_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("provider_snapshot_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch.add_column(
            sa.Column("generation_settings_json", sa.Text(), nullable=False, server_default="{}")
        )
    op.create_table(
        "generation_revisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "generation_id",
            sa.String(64),
            sa.ForeignKey("generations.id", ondelete="CASCADE"),
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("generation_id", "revision", name="uq_generation_revision"),
    )
    op.create_index(
        "ix_generation_revisions_generation_id", "generation_revisions", ["generation_id"]
    )


def downgrade() -> None:
    # InkFlow never performs destructive automatic downgrades.
    pass
