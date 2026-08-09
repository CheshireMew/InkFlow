from __future__ import annotations

import json
from pathlib import Path


def test_repository_and_synchronized_prompt_licenses_have_explicit_boundaries() -> None:
    repository = Path(__file__).resolve().parents[1]
    licensing = (repository / "LICENSING.md").read_text(encoding="utf-8")
    notices = (repository / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    prompt_licensing = (
        repository / "src" / "inkflow" / "prompt_files" / "LICENSING.md"
    ).read_text(encoding="utf-8")

    assert "SPDX-License-Identifier: AGPL-3.0-or-later" in licensing
    assert "Mozilla Public License 2.0" in notices
    assert "https://mozilla.org/MPL/2.0/" in notices
    assert "100x-working-tree" in prompt_licensing
    assert "100x-git-history" in prompt_licensing
    assert "100x-archived-git-history" in prompt_licensing

    synchronized = []
    for path in (repository / "src" / "inkflow" / "prompt_files").rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        source_kind = payload.get("source", {}).get("kind")
        if source_kind in {
            "100x-working-tree",
            "100x-git-history",
            "100x-archived-git-history",
        }:
            synchronized.append(path)
    assert synchronized
