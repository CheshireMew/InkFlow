from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from inkflow.storage import Database


def test_real_0001_database_migrates_without_legacy_job_fields(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "src" / "inkflow" / "migrations"),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "0001_initial")
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, title, user_request, created_at, updated_at) "
                "VALUES ('project-old', '旧项目', '原要求', '2026-01-01', '2026-01-01')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO provider_profiles "
                "(id, name, adapter, base_url, model, capabilities_json, parameters_json, "
                "secret_key_name, active, created_at) VALUES "
                "('provider-old', '旧配置', 'openai-compatible-chat', "
                "'https://example.invalid/v1', "
                "'old-model', '{}', '{}', 'old-secret', 1, '2026-01-01')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO jobs "
                "(id, project_id, kind, executor, status, payload_json, input_hash, lease_token, "
                "leased_at, attempt, created_at) VALUES "
                "('job-old', 'project-old', 'prepare_material', 'external', 'leased', '{}', "
                "'old-hash', 'old-token', '2026-01-01', 1, '2026-01-01')"
            )
        )
    database = Database(database_path)
    database.initialize()
    inspector = sa.inspect(database.engine)
    job_columns = {column["name"] for column in inspector.get_columns("jobs")}
    assert not {"lease_token", "leased_at", "attempt", "result_json", "error"} & job_columns
    with database.engine.connect() as connection:
        attempt = connection.execute(
            sa.text("SELECT job_id, attempt, lease_token FROM job_attempts WHERE job_id='job-old'")
        ).mappings().one()
        provider = connection.execute(
            sa.text(
                "SELECT revision, config_hash FROM provider_profiles WHERE id='provider-old'"
            )
        ).mappings().one()
        assert dict(attempt) == {"job_id": "job-old", "attempt": 1, "lease_token": "old-token"}
        assert provider["revision"] == 1
        assert len(provider["config_hash"]) == 64
        assert database.diagnostics()["schema_version"] == "3"
