"""Version project inputs and make stale task results terminal."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_project_input_lifecycle"
down_revision = "0005_execution_review_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column("input_revision", sa.Integer(), nullable=False, server_default="1")
        )
    with op.batch_alter_table("handoff_revisions") as batch:
        batch.add_column(
            sa.Column(
                "project_input_revision",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
    op.execute(sa.text("UPDATE schema_meta SET value='6' WHERE key='schema_version'"))


def downgrade() -> None:
    raise RuntimeError("project input revisions are intentionally irreversible")
