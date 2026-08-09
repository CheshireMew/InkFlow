from __future__ import annotations

from typing import Any

from inkflow.__about__ import __version__
from inkflow.application.experiments import Experiments
from inkflow.application.handoffs import Handoffs
from inkflow.application.jobs import JobCoordinator
from inkflow.application.project_inputs import ProjectInputs
from inkflow.application.provider_runtime import ProviderRuntime
from inkflow.application.result_queries import ResultQueries
from inkflow.runtime_logging import ai_audit_path, configure_ai_audit
from inkflow.storage import (
    Database,
    LibraryStore,
    ProjectStore,
    PromptStore,
    ProviderStore,
    ResultStore,
    WorkflowStore,
)


class InkFlowService:
    """Composition root exposing explicit application and persistence boundaries."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        self.projects = ProjectStore(database)
        self.library = LibraryStore(database)
        self.prompts = PromptStore(database)
        self.providers = ProviderStore(database)
        self.workflows = WorkflowStore(database)
        self.results = ResultStore(database)
        configure_ai_audit(database.path.parent / "logs" / "ai-interactions.jsonl")
        self.prompts.ensure_bundled()

        self.project_inputs = ProjectInputs(self.projects, self.library)
        self.provider_runtime = ProviderRuntime(self.providers)
        self.jobs = JobCoordinator(
            projects=self.projects,
            library=self.library,
            prompts=self.prompts,
            workflows=self.workflows,
            provider_runtime=self.provider_runtime,
        )
        self.handoffs = Handoffs(
            projects=self.projects,
            library=self.library,
            workflows=self.workflows,
        )
        self.experiments = Experiments(
            library=self.library,
            prompts=self.prompts,
            workflows=self.workflows,
            provider_runtime=self.provider_runtime,
        )
        self.result_queries = ResultQueries(self.results, self.workflows)

    def doctor(self) -> dict[str, Any]:
        diagnostics = self.database.diagnostics()
        diagnostics.update(
            {
                "ok": True,
                "version": __version__,
                "projects": len(self.projects.list()),
                "references": len(self.library.list_references(include_inactive=True)),
                "rules": len(self.library.list_rules()),
                "prompts": len(self.prompts.list()),
                "provider_profiles": len(self.providers.list()),
                "ai_audit_log": str(ai_audit_path()) if ai_audit_path() else None,
            }
        )
        return diagnostics
