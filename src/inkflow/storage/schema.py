from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    user_request: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class SourceRow(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40))


class ReferenceRow(Base):
    __tablename__ = "references"
    __table_args__ = (UniqueConstraint("body_hash", name="uq_references_body_hash"),)

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    body_hash: Mapped[str] = mapped_column(String(64), unique=True)
    formats_json: Mapped[str] = mapped_column(Text, default="[]")
    techniques_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    imported_at: Mapped[str] = mapped_column(String(40))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class WritingRuleRow(Base):
    __tablename__ = "writing_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    body_hash: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[str] = mapped_column(String(40))


class HandoffRow(Base):
    __tablename__ = "handoff_revisions"
    __table_args__ = (UniqueConstraint("project_id", "revision", name="uq_handoff_revision"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), index=True)
    user_request: Mapped[str] = mapped_column(Text)
    purified_material: Mapped[str] = mapped_column(Text)
    reference_case_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    reference_hook_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    reference_cases_json: Mapped[str] = mapped_column(Text, default="[]")
    reference_hooks_json: Mapped[str] = mapped_column(Text, default="[]")
    other_inputs: Mapped[str] = mapped_column(Text, default="无")
    core_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[str] = mapped_column(String(40))
    approved_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class ProviderProfileRow(Base):
    __tablename__ = "provider_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    adapter: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(200))
    capabilities_json: Mapped[str] = mapped_column(Text, default="{}")
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    secret_key_name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))


class ExperimentRow(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    handoff_id: Mapped[str] = mapped_column(ForeignKey("handoff_revisions.id"))
    kind: Mapped[str] = mapped_column(String(30))
    executor: Mapped[str] = mapped_column(String(20))
    provider_profile_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("provider_profiles.id"), nullable=True
    )
    fixed_input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class ExperimentArmRow(Base):
    __tablename__ = "experiment_arms"
    __table_args__ = (
        UniqueConstraint("experiment_id", "ordinal", name="uq_experiment_arm_ordinal"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    writing_rule_id: Mapped[str] = mapped_column(ForeignKey("writing_rules.id"))
    writing_rule_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), index=True)


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    handoff_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("handoff_revisions.id"), nullable=True
    )
    experiment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("experiments.id"), nullable=True, index=True
    )
    experiment_arm_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("experiment_arms.id"), nullable=True, unique=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    executor: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    lease_token: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)
    leased_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class GenerationRow(Base):
    __tablename__ = "generations"
    __table_args__ = (UniqueConstraint("job_id", "output_index", name="uq_generation_output"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    handoff_id: Mapped[str] = mapped_column(ForeignKey("handoff_revisions.id"))
    experiment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("experiments.id"), nullable=True
    )
    writing_rule_id: Mapped[str] = mapped_column(ForeignKey("writing_rules.id"))
    output_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executor_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))


Index("idx_jobs_project_status_created", JobRow.project_id, JobRow.status, JobRow.created_at)
Index(
    "idx_handoffs_project_status_revision",
    HandoffRow.project_id,
    HandoffRow.status,
    HandoffRow.revision,
)
