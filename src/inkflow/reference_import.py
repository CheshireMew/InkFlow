from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from inkflow.boundaries import strip_reference_wrapper
from inkflow.domain import ReferenceKind, stable_hash
from inkflow.storage.library import LibraryStore

CASE_METADATA = re.compile(
    r"\n?<!--\s*content-case-index\s*\n(?P<body>.*?)\n-->\s*$",
    re.DOTALL,
)
HOOK_METADATA = re.compile(
    r"\n?<!--\s*hook-library-index\s*\n(?P<body>\{.*\})\n-->\s*$",
    re.DOTALL,
)


@dataclass
class ImportReport:
    manifest_version: int = 2
    source_fingerprint: str = ""
    cases_discovered: int = 0
    hooks_discovered: int = 0
    rules_discovered: int = 0
    cases_imported: int = 0
    hooks_imported: int = 0
    rules_imported: int = 0
    duplicates: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "manifest_version": self.manifest_version,
            "source_fingerprint": self.source_fingerprint,
            "cases_discovered": self.cases_discovered,
            "hooks_discovered": self.hooks_discovered,
            "rules_discovered": self.rules_discovered,
            "cases_imported": self.cases_imported,
            "hooks_imported": self.hooks_imported,
            "rules_imported": self.rules_imported,
            "duplicates": self.duplicates,
            "invalid": self.invalid,
        }


@dataclass(frozen=True)
class ReferenceSource:
    path: Path
    relative_path: str
    raw: str


@dataclass(frozen=True)
class ReferenceImportSnapshot:
    cases: tuple[tuple[ReferenceSource, str], ...]
    hooks: tuple[ReferenceSource, ...]
    writing_rule: tuple[ReferenceSource, str] | None
    fingerprint: str


def import_100x_library(library: LibraryStore, library_root: Path) -> ImportReport:
    root = library_root.resolve()
    if not (root / "Home.md").is_file():
        raise FileNotFoundError(f"100x library marker not found: {root / 'Home.md'}")

    snapshot = _snapshot_sources(root)
    report = ImportReport(
        source_fingerprint=snapshot.fingerprint,
        cases_discovered=len(snapshot.cases),
        hooks_discovered=len(snapshot.hooks),
        rules_discovered=int(snapshot.writing_rule is not None),
    )
    _import_cases(library, snapshot.cases, report)
    _import_hooks(library, snapshot.hooks, report)
    _import_writing_rule(library, snapshot.writing_rule, report)
    return report


def _import_cases(
    library: LibraryStore,
    sources: tuple[tuple[ReferenceSource, str], ...],
    report: ImportReport,
) -> None:
    for source, writing_format in sources:
        try:
            raw = source.raw
            match = CASE_METADATA.search(raw)
            if not match:
                raise ValueError("missing content-case-index")
            metadata = _parse_case_metadata(match.group("body"))
            reference_id = _strip_quotes(metadata.get("case_id", ""))
            techniques = _parse_inline_list(metadata.get("writing_techniques", "[]"))
            title, body = strip_reference_wrapper(raw, section_heading="原文全文")
            _reject_existing_reference(library, reference_id, body)
            library.add_reference(
                reference_id=reference_id,
                kind=ReferenceKind.CASE,
                title=title,
                body=body,
                formats=[writing_format],
                techniques=techniques,
                metadata={"imported_from": "100x-learning"},
            )
            report.cases_imported += 1
        except ValueError as exc:
            message = f"{source.relative_path}: {exc}"
            _record_import_error(report, message, exc)


def _import_hooks(
    library: LibraryStore,
    sources: tuple[ReferenceSource, ...],
    report: ImportReport,
) -> None:
    for source in sources:
        try:
            raw = source.raw
            match = HOOK_METADATA.search(raw)
            if not match:
                raise ValueError("missing hook-library-index")
            metadata = json.loads(match.group("body"))
            reference_id = str(metadata.get("hook_id") or source.path.stem)
            formats = metadata.get("writing_formats") or []
            technique = source.path.parent.name
            title, body = strip_reference_wrapper(raw, section_heading="钩子原文")
            _reject_existing_reference(library, reference_id, body)
            library.add_reference(
                reference_id=reference_id,
                kind=ReferenceKind.HOOK,
                title=title,
                body=body,
                formats=[str(item) for item in formats],
                techniques=[technique],
                metadata={"imported_from": "100x-learning"},
            )
            report.hooks_imported += 1
        except (ValueError, json.JSONDecodeError) as exc:
            message = f"{source.relative_path}: {exc}"
            _record_import_error(report, message, exc)


def _import_writing_rule(
    library: LibraryStore,
    writing_rule: tuple[ReferenceSource, str] | None,
    report: ImportReport,
) -> None:
    if writing_rule is None:
        return
    source, body = writing_rule
    if library.find_rule_by_body_hash(stable_hash(body)) is not None:
        report.duplicates.append(
            f"{source.relative_path}: writing rule already imported"
        )
        return
    library.add_rule(name="100x 正式写作规则", body=body, activate=True)
    report.rules_imported += 1


def _snapshot_sources(root: Path) -> ReferenceImportSnapshot:
    sources = root / "20-Sources"
    case_locations = [
        (sources / "Social Posts" / "Content Cases" / "完整短内容", "short"),
        (sources / "Articles" / "Content Cases", "article"),
    ]
    cases: list[tuple[ReferenceSource, str]] = []
    for directory, writing_format in case_locations:
        if directory.is_dir():
            cases.extend(
                (_read_source(root, path), writing_format)
                for path in sorted(directory.rglob("*.md"))
            )
    hook_directory = sources / "Hook Library" / "Examples"
    hooks = (
        tuple(_read_source(root, path) for path in sorted(hook_directory.rglob("*.md")))
        if hook_directory.is_dir()
        else ()
    )
    writing_rule_path = root.parent / "references" / "content-writing.md"
    writing_rule_source = (
        _read_source(root.parent, writing_rule_path)
        if writing_rule_path.is_file()
        else None
    )
    writing_rule_body = _extract_writing_rule(writing_rule_source)
    writing_rule = (
        (writing_rule_source, writing_rule_body)
        if writing_rule_source is not None and writing_rule_body is not None
        else None
    )
    entries = [
        {
            "kind": "case",
            "format": writing_format,
            "path": source.relative_path,
            "content_hash": stable_hash(source.raw),
        }
        for source, writing_format in cases
    ] + [
        {
            "kind": "hook",
            "path": source.relative_path,
            "content_hash": stable_hash(source.raw),
        }
        for source in hooks
    ]
    if writing_rule_source is not None:
        entries.append(
            {
                "kind": "writing_rule",
                "path": writing_rule_source.relative_path,
                "content_hash": stable_hash(writing_rule_source.raw),
            }
        )
    return ReferenceImportSnapshot(
        cases=tuple(cases),
        hooks=hooks,
        writing_rule=writing_rule,
        fingerprint=stable_hash({"manifest_version": 2, "entries": entries}),
    )


def _extract_writing_rule(source: ReferenceSource | None) -> str | None:
    if source is None:
        return None
    match = re.search(
        r"【写作规则】\s*\n(?P<body>.*?)(?:\n\s*【净化后材料】)",
        source.raw,
        re.DOTALL,
    )
    if not match:
        return None
    body = match.group("body").strip()
    if not body or (body.startswith("<") and body.endswith(">")):
        return None
    return body


def _read_source(relative_root: Path, path: Path) -> ReferenceSource:
    return ReferenceSource(
        path=path,
        relative_path=path.relative_to(relative_root).as_posix(),
        raw=path.read_text(encoding="utf-8-sig"),
    )


def _parse_case_metadata(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"invalid metadata line: {line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def _parse_inline_list(value: str) -> list[str]:
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        raise ValueError("writing_techniques must be an inline list")
    return [
        _strip_quotes(item)
        for item in next(csv.reader([stripped[1:-1]], skipinitialspace=True))
        if _strip_quotes(item)
    ]


def _strip_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1].strip()
    return stripped


def _reject_existing_reference(library: LibraryStore, reference_id: str, body: str) -> None:
    if not reference_id.strip():
        raise ValueError("missing reference id")
    existing = library.find_reference(reference_id)
    if existing is not None:
        raise ValueError(f"reference id already exists: {reference_id}")
    body_hash = stable_hash(body.strip())
    duplicate = next(
        (
            row
            for row in library.list_references(include_inactive=True)
            if row.body_hash == body_hash
        ),
        None,
    )
    if duplicate is not None:
        raise ValueError(f"reference body duplicates {duplicate.id}")


def _record_import_error(report: ImportReport, message: str, exc: Exception) -> None:
    reason = str(exc).lower()
    if "duplicate" in reason or "already exists" in reason:
        report.duplicates.append(message)
    else:
        report.invalid.append(message)
