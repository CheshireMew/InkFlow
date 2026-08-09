from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update

from inkflow.domain import ProviderSnapshot, stable_hash
from inkflow.storage.common import dumps, loads, now
from inkflow.storage.database import Database
from inkflow.storage.schema import ProviderProfileRow


class ProviderStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add(
        self,
        *,
        profile_id: str,
        name: str,
        adapter: str,
        base_url: str,
        model: str,
        capabilities: dict[str, Any],
        parameters: dict[str, Any],
        secret_key_name: str,
        activate: bool,
    ) -> ProviderProfileRow:
        if not all([name.strip(), adapter.strip(), base_url.strip(), model.strip()]):
            raise ValueError("provider name, adapter, base URL and model are required")
        with self.database.transaction() as session:
            revision = session.scalar(
                select(func.max(ProviderProfileRow.revision)).where(
                    ProviderProfileRow.name == name.strip()
                )
            )
            revision_number = int(revision or 0) + 1
            snapshot_payload = {
                "name": name.strip(),
                "revision": revision_number,
                "adapter": adapter,
                "base_url": base_url.rstrip("/"),
                "model": model.strip(),
                "capabilities": capabilities,
                "parameters": parameters,
            }
            if activate:
                session.execute(update(ProviderProfileRow).values(active=False))
            row = ProviderProfileRow(
                id=profile_id,
                name=name.strip(),
                revision=revision_number,
                adapter=adapter,
                base_url=base_url.rstrip("/"),
                model=model.strip(),
                capabilities_json=dumps(capabilities),
                parameters_json=dumps(parameters),
                secret_key_name=secret_key_name,
                config_hash=stable_hash(snapshot_payload),
                active=activate,
                created_at=now(),
            )
            session.add(row)
        return row

    def list(self) -> list[ProviderProfileRow]:
        with self.database.session() as session:
            rows = list(
                session.scalars(
                    select(ProviderProfileRow).order_by(
                        ProviderProfileRow.created_at.desc(), ProviderProfileRow.id
                    )
                )
            )
            for row in rows:
                session.expunge(row)
            return rows

    def get(self, profile_id: str | None = None) -> ProviderProfileRow:
        with self.database.session() as session:
            row = (
                session.get(ProviderProfileRow, profile_id)
                if profile_id
                else session.scalar(
                    select(ProviderProfileRow).where(ProviderProfileRow.active.is_(True))
                )
            )
            if row is None:
                raise FileNotFoundError("Provider profile not found")
            session.expunge(row)
            return row

    def activate(self, profile_id: str) -> ProviderProfileRow:
        with self.database.transaction() as session:
            row = session.get(ProviderProfileRow, profile_id)
            if row is None:
                raise FileNotFoundError(f"Provider profile not found: {profile_id}")
            session.execute(update(ProviderProfileRow).values(active=False))
            row.active = True
            session.flush()
            session.expunge(row)
            return row

    @staticmethod
    def snapshot(row: ProviderProfileRow) -> ProviderSnapshot:
        return ProviderSnapshot(
            id=row.id,
            name=row.name,
            revision=row.revision,
            adapter=row.adapter,
            base_url=row.base_url,
            model=row.model,
            capabilities=loads(row.capabilities_json, {}),
            parameters=loads(row.parameters_json, {}),
            config_hash=row.config_hash,
        )
