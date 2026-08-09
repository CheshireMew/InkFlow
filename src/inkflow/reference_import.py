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
    cases_imported: int = 0
    hooks_imported: int = 0
    rules_imported: int = 0
    duplicates: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "cases_imported": self.cases_imported,
            "hooks_imported": self.hooks_imported,
            "rules_imported": self.rules_imported,
            "duplicates": self.duplicates,
            "invalid": self.invalid,
        }


def import_100x_library(library: LibraryStore, library_root: Path) -> ImportReport:
    root = library_root.resolve()
    if not (root / "Home.md").is_file():
        raise FileNotFoundError(f"100x library marker not found: {root / 'Home.md'}")

    report = ImportReport()
    _import_cases(library, root, report)
    _import_hooks(library, root, report)
    _import_writing_rule(library, root, report)
    return report


def _import_cases(library: LibraryStore, root: Path, report: ImportReport) -> None:
    sources = root / "20-Sources"
    locations = [
        (sources / "Social Posts" / "Content Cases" / "完整短内容", "short"),
        (sources / "Articles" / "Content Cases", "article"),
    ]
    for directory, writing_format in locations:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.md")):
            try:
                raw = path.read_text(encoding="utf-8-sig")
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
                message = f"{path.name}: {exc}"
                _record_import_error(report, message, exc)


def _import_hooks(library: LibraryStore, root: Path, report: ImportReport) -> None:
    directory = root / "20-Sources" / "Hook Library" / "Examples"
    if not directory.is_dir():
        return
    for path in sorted(directory.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8-sig")
            match = HOOK_METADATA.search(raw)
            if not match:
                raise ValueError("missing hook-library-index")
            metadata = json.loads(match.group("body"))
            reference_id = str(metadata.get("hook_id") or path.stem)
            formats = metadata.get("writing_formats") or []
            technique = path.parent.name
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
            message = f"{path.name}: {exc}"
            _record_import_error(report, message, exc)


def _import_writing_rule(library: LibraryStore, root: Path, report: ImportReport) -> None:
    content_writing = root.parent / "references" / "content-writing.md"
    if not content_writing.is_file():
        return
    text = content_writing.read_text(encoding="utf-8-sig")
    match = re.search(r"【写作规则】\s*\n(?P<body>.*?)(?:\n\s*【净化后材料】)", text, re.DOTALL)
    if not match:
        report.invalid.append("content-writing.md: writing rule section not found")
        return
    body = match.group("body").strip()
    if body.startswith("<") and body.endswith(">"):
        report.invalid.append("content-writing.md: writing rule is a placeholder")
        return
    if library.find_rule_by_body_hash(stable_hash(body)) is not None:
        report.duplicates.append("content-writing.md: writing rule already imported")
        return
    library.add_rule(name="100x 正式写作规则", body=body, activate=True)
    report.rules_imported += 1


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
