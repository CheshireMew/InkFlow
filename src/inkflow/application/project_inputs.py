from __future__ import annotations

from pathlib import Path
from typing import Any

from inkflow.reference_import import ImportReport, import_100x_library
from inkflow.source_import import extract_url
from inkflow.storage import LibraryStore, ProjectStore


class ProjectInputs:
    def __init__(self, projects: ProjectStore, library: LibraryStore) -> None:
        self.projects = projects
        self.library = library

    def import_100x(self, library_root: Path) -> ImportReport:
        return import_100x_library(self.library, library_root)

    def create_project(
        self, *, title: str, user_request: str, materials: list[tuple[str, str]]
    ) -> str:
        project = self.projects.create_with_sources(
            title=title,
            user_request=user_request,
            sources=[
                (
                    "file" if source_name else "pasted",
                    content,
                    {"source_name": source_name} if source_name else {},
                )
                for source_name, content in materials
            ],
        )
        return project.id

    def update_request(self, project_id: str, user_request: str) -> None:
        self.projects.update_request(project_id, user_request)

    def add_source(
        self, project_id: str, *, content: str, kind: str, provenance: dict[str, Any]
    ) -> str:
        return self.projects.add_source(
            project_id, kind=kind, content=content, provenance=provenance
        ).id

    def add_url_source(self, project_id: str, url: str) -> str:
        content, provenance = extract_url(url)
        return self.add_source(
            project_id, content=content, kind="url", provenance=provenance
        )

    def update_source(self, project_id: str, source_id: str, content: str) -> None:
        self.projects.update_source(project_id, source_id, content)
