from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.path.as_posix()}",
            future=True,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        event.listen(self.engine, "connect", _configure_sqlite)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False, class_=Session)

    def initialize(self) -> None:
        config = self._alembic_config()
        self._refuse_unknown_schema(config)
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.path.as_posix()}")
        command.upgrade(config, "head")
        with self.engine.connect() as connection:
            version = connection.scalar(
                text("SELECT value FROM schema_meta WHERE key='schema_version'")
            )
            if version != "3":
                raise RuntimeError(f"unsupported InkFlow schema version after upgrade: {version}")

    def session(self) -> Session:
        return self.sessions()

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[Session]:
        session = self.sessions()
        try:
            if immediate:
                session.execute(text("BEGIN IMMEDIATE"))
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def diagnostics(self) -> dict[str, object]:
        with self.engine.connect() as connection:
            return {
                "path": str(self.path),
                "schema_version": connection.scalar(
                    text("SELECT value FROM schema_meta WHERE key='schema_version'")
                ),
                "alembic_revision": connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                ),
                "journal_mode": connection.scalar(text("PRAGMA journal_mode")),
                "foreign_keys": bool(connection.scalar(text("PRAGMA foreign_keys"))),
            }

    def _alembic_config(self) -> Config:
        config = Config()
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
        )
        return config

    def _refuse_unknown_schema(self, config: Config) -> None:
        if "alembic_version" not in inspect(self.engine).get_table_names():
            return
        with self.engine.connect() as connection:
            current = connection.scalar(text("SELECT version_num FROM alembic_version"))
        known = {
            revision.revision for revision in ScriptDirectory.from_config(config).walk_revisions()
        }
        if current and current not in known:
            raise RuntimeError(
                f"database schema {current!r} is newer than this InkFlow build; upgrade InkFlow"
            )


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()
