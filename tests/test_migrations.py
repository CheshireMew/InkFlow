from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from inkflow.storage import Database


def test_historical_migrations_do_not_import_current_runtime_code() -> None:
    versions = Path(__file__).resolve().parents[1] / "src" / "inkflow" / "migrations" / "versions"
    for path in versions.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from inkflow" not in text, path.name
        assert "import inkflow" not in text, path.name


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
        assert database.diagnostics()["schema_version"] == "6"
    table_names = set(inspector.get_table_names())
    assert "prompts" in table_names
    assert "prompt_revisions" not in table_names
    prompt_columns = {column["name"] for column in inspector.get_columns("prompts")}
    assert prompt_columns == {
        "stage",
        "current_file",
        "contract_version",
        "document_hash",
        "prompt_hash",
        "origin",
        "updated_at",
    }
    experiment_columns = {column["name"] for column in inspector.get_columns("experiments")}
    assert "prompt_revision_id" not in experiment_columns
    assert "input_package_hash" in experiment_columns
    assert "fixed_input_hash" not in experiment_columns
    generation_columns = {column["name"] for column in inspector.get_columns("generations")}
    assert "review_state" in generation_columns
    assert "selected" not in generation_columns
    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    assert "input_revision" in project_columns
    handoff_columns = {
        column["name"] for column in inspector.get_columns("handoff_revisions")
    }
    assert "project_input_revision" in handoff_columns


def test_schema_4_selected_results_become_explicit_review_states(tmp_path: Path) -> None:
    database_path = tmp_path / "schema4.sqlite3"
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "src" / "inkflow" / "migrations"),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "0004_current_prompts")
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO projects (id, title, user_request, created_at, updated_at) "
                "VALUES ('project-review', '审阅迁移', '写作', '2026-01-01', '2026-01-01')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO writing_rules "
                "(id, name, revision, body, body_hash, active, created_at) VALUES "
                "('rule-review', '规则', 1, '直接写', 'rule-hash', 1, '2026-01-01')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO handoff_revisions "
                "(id, project_id, revision, status, user_request, purified_material, "
                "reference_case_ids_json, reference_hook_ids_json, reference_cases_json, "
                "reference_hooks_json, other_inputs, core_hash, created_at) VALUES "
                "('handoff-review', 'project-review', 1, 'approved', '写作', '材料', "
                "'[]', '[]', '[]', '[]', '无', 'core-hash', '2026-01-01')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO experiments "
                "(id, project_id, handoff_id, kind, executor, prompt_snapshot_json, "
                "provider_snapshot_json, generation_settings_json, fixed_input_hash, status, "
                "created_at) VALUES ('experiment-review', 'project-review', 'handoff-review', "
                "'batch_five', 'external', '{}', '{}', '{}', 'input-hash', 'completed', "
                "'2026-01-01')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO jobs "
                "(id, project_id, handoff_id, experiment_id, kind, executor, status, "
                "payload_json, input_hash, created_at) VALUES ('job-review', 'project-review', "
                "'handoff-review', 'experiment-review', 'generate', 'external', 'succeeded', "
                "'{}', 'job-hash', '2026-01-01')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO generations "
                "(id, project_id, job_id, handoff_id, experiment_id, writing_rule_id, "
                "output_index, content, executor_metadata_json, prompt_snapshot_json, "
                "provider_snapshot_json, generation_settings_json, selected, created_at) VALUES "
                "('generation-accepted', 'project-review', 'job-review', 'handoff-review', "
                "'experiment-review', 'rule-review', 0, '接受内容', '{}', '{}', '{}', '{}', 1, "
                "'2026-01-01'), ('generation-unreviewed', 'project-review', 'job-review', "
                "'handoff-review', 'experiment-review', 'rule-review', 1, '未审阅内容', '{}', "
                "'{}', '{}', '{}', 0, '2026-01-01')"
            )
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        experiment = connection.execute(
            sa.text("SELECT input_package_hash FROM experiments")
        ).scalar_one()
        states = connection.execute(
            sa.text("SELECT id, review_state FROM generations ORDER BY id")
        ).mappings().all()
    assert experiment == "input-hash"
    assert [dict(row) for row in states] == [
        {"id": "generation-accepted", "review_state": "accepted"},
        {"id": "generation-unreviewed", "review_state": "unreviewed"},
    ]


def test_schema_3_prompt_history_becomes_one_current_file_without_deleting_assets(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "schema3.sqlite3"
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "src" / "inkflow" / "migrations"),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "0003_prompt_entities")
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT id, stage, name, revision, system_prompt, user_template, "
                "contract_version, entity_file FROM prompt_revisions "
                "WHERE stage='prepare_material' AND active=1"
            )
        ).mappings().one()

    prompt_root = database_path.parent / "prompts"
    immutable_asset = prompt_root / row["entity_file"]
    assert immutable_asset.is_file()
    current_path = prompt_root / "current" / "prepare_material.prompt.json"
    current_path.parent.mkdir(parents=True, exist_ok=True)
    current_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": row["id"],
                "stage": row["stage"],
                "name": "迁移前手改的当前提示词",
                "system_prompt": "只保留当前任务真正需要的材料。",
                "user_template": row["user_template"],
                "contract_version": row["contract_version"],
                "revision": row["revision"],
                "default_active": False,
                "source": {"kind": "user-current-file"},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    command.upgrade(config, "head")
    migrated = json.loads(current_path.read_text(encoding="utf-8"))
    assert migrated == {
        "schema_version": 2,
        "stage": "prepare_material",
        "name": "迁移前手改的当前提示词",
        "system_prompt": "只保留当前任务真正需要的材料。",
        "user_template": row["user_template"],
    }
    assert immutable_asset.is_file()
    with engine.connect() as connection:
        current = connection.execute(
            sa.text("SELECT stage, origin FROM prompts WHERE stage='prepare_material'")
        ).mappings().one()
        assert dict(current) == {"stage": "prepare_material", "origin": "user"}
        assert connection.execute(
            sa.text("SELECT count(*) FROM prompts WHERE stage='prepare_material'")
        ).scalar_one() == 1
