from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
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
        config = Config()
        config.set_main_option(
            "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
        )
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.path.as_posix()}")
        command.upgrade(config, "head")

    def session(self) -> Session:
        return self.sessions()


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()
