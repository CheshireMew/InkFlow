from __future__ import annotations

import sys
from pathlib import Path


def frontend_dist() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "frontend" / "dist"
    installed = Path(__file__).resolve().parent / "frontend_dist"
    if installed.is_dir():
        return installed
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def prompt_files() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "inkflow" / "prompt_files"
    return Path(__file__).resolve().parent / "prompt_files"
