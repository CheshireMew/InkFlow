from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_log_path: Path | None = None


def configure_ai_audit(path: Path) -> Path:
    global _log_path
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    _log_path = resolved
    return resolved


def ai_audit_path() -> Path | None:
    return _log_path


def log_ai_event(event: str, interaction_id: str, **fields: Any) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": "INFO",
        "component": "inkflow.ai",
        "event": event,
        "interaction_id": interaction_id,
        **fields,
    }
    encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _lock:
        print(encoded, file=sys.stderr, flush=True)
        if _log_path is not None:
            with _log_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(encoded + "\n")
