from __future__ import annotations

from pathlib import Path

import pytest

from inkflow.reference_import import import_100x_library
from inkflow.storage import Database, Repository

REAL_100X_LIBRARY = Path(r"E:\Work\BaiduSyncdisk\Code\100x-learning\System Knowledge")


@pytest.mark.skipif(
    not (REAL_100X_LIBRARY / "Home.md").is_file(), reason="local 100x library is unavailable"
)
def test_real_100x_import_is_read_only_idempotent_and_strips_wrappers(tmp_path: Path) -> None:
    repository = Repository(Database(tmp_path / "inkflow.sqlite3"))
    repository.database.initialize()

    first = import_100x_library(repository, REAL_100X_LIBRARY)
    assert first.cases_imported == 34
    assert first.hooks_imported == 7
    assert first.rules_imported == 1
    assert len(first.duplicates) == 1
    assert first.invalid == []

    references = repository.list_references()
    assert len(references) == 41
    assert all("## 原文全文" not in row.body for row in references)
    assert all("## 钩子原文" not in row.body for row in references)
    assert all("content-case-index" not in row.body for row in references)
    assert all("hook-library-index" not in row.body for row in references)

    second = import_100x_library(repository, REAL_100X_LIBRARY)
    assert second.cases_imported == 0
    assert second.hooks_imported == 0
    assert second.rules_imported == 0
    assert second.invalid == []
    assert len(second.duplicates) == 43
    assert len(repository.list_references()) == 41
    assert len(repository.list_rules()) == 1
