from __future__ import annotations

import json
from typing import Any


def row_dict(row: Any, *, omit: set[str] | None = None) -> dict[str, Any]:
    excluded = omit or set()
    result: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.name in excluded:
            continue
        value = getattr(row, column.name)
        if column.name.endswith("_json") and value:
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        result[column.name] = value
    return result
