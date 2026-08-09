from __future__ import annotations

import os
from pathlib import Path

import pytest

from inkflow.reference_import import import_100x_library
from inkflow.storage import Database, LibraryStore

REAL_100X_LIBRARY = Path(os.environ.get("INKFLOW_100X_LIBRARY", "__missing_100x_library__"))
FIXTURE_LIBRARY = (
    Path(__file__).parent / "fixtures" / "100x-repository" / "System Knowledge"
)


def test_versioned_import_contract_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    library = LibraryStore(Database(tmp_path / "inkflow.sqlite3"))
    library.database.initialize()

    first = import_100x_library(library, FIXTURE_LIBRARY)
    assert first.manifest_version == 2
    assert len(first.source_fingerprint) == 64
    assert first.cases_discovered == first.cases_imported == 1
    assert first.hooks_discovered == first.hooks_imported == 1
    assert first.rules_discovered == first.rules_imported == 1
    assert first.duplicates == []
    assert first.invalid == []

    second = import_100x_library(library, FIXTURE_LIBRARY)
    assert second.source_fingerprint == first.source_fingerprint
    assert second.cases_imported == 0
    assert second.hooks_imported == 0
    assert second.rules_imported == 0
    assert second.invalid == []
    assert len(second.duplicates) == 3
    assert len(library.list_references()) == 2
    assert len(library.list_rules()) == 1


@pytest.mark.skipif(
    not (REAL_100X_LIBRARY / "Home.md").is_file(), reason="local 100x library is unavailable"
)
def test_real_100x_import_is_read_only_idempotent_and_strips_wrappers(tmp_path: Path) -> None:
    library = LibraryStore(Database(tmp_path / "inkflow.sqlite3"))
    library.database.initialize()

    first = import_100x_library(library, REAL_100X_LIBRARY)
    assert first.manifest_version == 2
    assert len(first.source_fingerprint) == 64
    assert first.cases_discovered >= first.cases_imported > 0
    assert first.hooks_discovered >= first.hooks_imported > 0
    assert first.rules_imported == first.rules_discovered
    assert first.invalid == []

    references = library.list_references()
    assert len(references) == first.cases_imported + first.hooks_imported
    assert all("## 原文全文" not in row.body for row in references)
    assert all("## 钩子原文" not in row.body for row in references)
    assert all("content-case-index" not in row.body for row in references)
    assert all("hook-library-index" not in row.body for row in references)

    second = import_100x_library(library, REAL_100X_LIBRARY)
    assert second.cases_imported == 0
    assert second.hooks_imported == 0
    assert second.rules_imported == 0
    assert second.invalid == []
    assert second.source_fingerprint == first.source_fingerprint
    assert len(second.duplicates) >= len(references)
    assert len(library.list_references()) == len(references)
    assert len(library.list_rules()) == first.rules_imported
