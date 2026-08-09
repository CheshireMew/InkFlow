"""Create the original InkFlow writing workbench schema.

The migration owns a frozen schema.  It deliberately does not import the current ORM
metadata, so a fresh database follows the same upgrade path as an existing one.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("user_request", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "references",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("formats_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("techniques_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("imported_at", sa.String(40), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("body_hash", name="uq_references_body_hash"),
    )
    op.create_index("ix_references_kind", "references", ["kind"])
    op.create_index("ix_references_body_hash", "references", ["body_hash"])
    op.create_index("ix_references_active", "references", ["active"])
    op.create_table(
        "writing_rules",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_writing_rules_name", "writing_rules", ["name"])
    op.create_index("ix_writing_rules_body_hash", "writing_rules", ["body_hash"])
    op.create_index("ix_writing_rules_active", "writing_rules", ["active"])
    op.create_table(
        "provider_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("adapter", sa.String(80), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("parameters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("secret_key_name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_sources_project_id", "sources", ["project_id"])
    op.create_index("ix_sources_content_hash", "sources", ["content_hash"])
    op.create_table(
        "handoff_revisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("user_request", sa.Text(), nullable=False),
        sa.Column("purified_material", sa.Text(), nullable=False),
        sa.Column("reference_case_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reference_hook_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reference_cases_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reference_hooks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("other_inputs", sa.Text(), nullable=False, server_default="无"),
        sa.Column("core_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("approved_at", sa.String(40)),
        sa.UniqueConstraint("project_id", "revision", name="uq_handoff_revision"),
    )
    op.create_index("ix_handoff_revisions_project_id", "handoff_revisions", ["project_id"])
    op.create_index("ix_handoff_revisions_status", "handoff_revisions", ["status"])
    op.create_index("ix_handoff_revisions_core_hash", "handoff_revisions", ["core_hash"])
    op.create_index(
        "idx_handoffs_project_status_revision",
        "handoff_revisions",
        ["project_id", "status", "revision"],
    )
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("handoff_id", sa.String(64), sa.ForeignKey("handoff_revisions.id")),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("executor", sa.String(20), nullable=False),
        sa.Column("provider_profile_id", sa.String(64), sa.ForeignKey("provider_profiles.id")),
        sa.Column("fixed_input_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.String(40)),
    )
    op.create_index("ix_experiments_project_id", "experiments", ["project_id"])
    op.create_index("ix_experiments_status", "experiments", ["status"])
    op.create_table(
        "experiment_arms",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "experiment_id", sa.String(64), sa.ForeignKey("experiments.id", ondelete="CASCADE")
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("writing_rule_id", sa.String(64), sa.ForeignKey("writing_rules.id")),
        sa.Column("writing_rule_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("experiment_id", "ordinal", name="uq_experiment_arm_ordinal"),
    )
    op.create_index("ix_experiment_arms_experiment_id", "experiment_arms", ["experiment_id"])
    op.create_index("ix_experiment_arms_status", "experiment_arms", ["status"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("handoff_id", sa.String(64), sa.ForeignKey("handoff_revisions.id")),
        sa.Column("experiment_id", sa.String(64), sa.ForeignKey("experiments.id")),
        sa.Column(
            "experiment_arm_id", sa.String(64), sa.ForeignKey("experiment_arms.id"), unique=True
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("executor", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("lease_token", sa.String(96)),
        sa.Column("leased_at", sa.String(40)),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("completed_at", sa.String(40)),
    )
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
    op.create_index("ix_jobs_experiment_id", "jobs", ["experiment_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_input_hash", "jobs", ["input_hash"])
    op.create_index(
        "idx_jobs_project_status_created", "jobs", ["project_id", "status", "created_at"]
    )
    op.create_table(
        "generations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("jobs.id", ondelete="CASCADE")),
        sa.Column("handoff_id", sa.String(64), sa.ForeignKey("handoff_revisions.id")),
        sa.Column("experiment_id", sa.String(64), sa.ForeignKey("experiments.id")),
        sa.Column("writing_rule_id", sa.String(64), sa.ForeignKey("writing_rules.id")),
        sa.Column("output_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_response", sa.Text()),
        sa.Column("executor_metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("job_id", "output_index", name="uq_generation_output"),
    )
    op.create_index("ix_generations_project_id", "generations", ["project_id"])
    op.create_index("ix_generations_job_id", "generations", ["job_id"])


def downgrade() -> None:
    # InkFlow never performs destructive automatic downgrades.
    pass
