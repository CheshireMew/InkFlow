from __future__ import annotations

import sys
from pathlib import Path


def frontend_dist() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "frontend" / "dist"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"
