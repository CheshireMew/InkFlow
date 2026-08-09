"""Separate input identity, execution control and user review state."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_execution_review_contracts"
down_revision = "0004_current_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("experiments", recreate="always") as batch:
        batch.alter_column(
            "fixed_input_hash",
            new_column_name="input_package_hash",
            existing_type=sa.String(64),
            existing_nullable=False,
        )

    with op.batch_alter_table("generations") as batch:
        batch.add_column(
            sa.Column(
                "review_state",
                sa.String(20),
                nullable=False,
                server_default="unreviewed",
            )
        )
        batch.create_index("ix_generations_review_state", ["review_state"])

    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE generations SET review_state='accepted' WHERE selected=1")
    )

    with op.batch_alter_table("generations", recreate="always") as batch:
        batch.drop_column("selected")

    connection.execute(
        sa.text("UPDATE schema_meta SET value='5' WHERE key='schema_version'")
    )


def downgrade() -> None:
    # InkFlow does not destructively roll user review decisions back into the old boolean model.
    pass
