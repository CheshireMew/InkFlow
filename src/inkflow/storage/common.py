from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)
