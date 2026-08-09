from __future__ import annotations

from inkflow.boundaries import sanitize_handoff_material
from inkflow.domain import ExecutionPackage, HandoffCore
from inkflow.storage import LibraryStore, ProjectStore, WorkflowStore
from inkflow.storage.common import loads


class Handoffs:
    def __init__(
        self,
        *,
        projects: ProjectStore,
        library: LibraryStore,
        workflows: WorkflowStore,
    ) -> None:
        self.projects = projects
        self.library = library
        self.workflows = workflows

    def approve(self, project_id: str):
        return self.workflows.approve_handoff(project_id)

    def render(self, project_id: str, *, rule_id: str | None = None) -> str:
        row = self.workflows.get_handoff(project_id)
        core = self.workflows.handoff_core(row)
        rule = self.library.get_rule(rule_id)
        return ExecutionPackage(handoff=core, writing_rule=rule.body).render()

    def revise(self, project_id: str, core: HandoffCore):
        project = self.projects.get(project_id)
        if core.user_request != project.user_request:
            raise ValueError(
                "user request can only be changed through the project request boundary"
            )
        latest = self.workflows.get_handoff(project_id)
        sanitized = sanitize_handoff_material(core.purified_material)
        if not sanitized:
            raise ValueError("purified material cannot be empty")
        revised = core.model_copy(update={"purified_material": sanitized})
        return self.workflows.create_handoff_revision(
            project_id=project_id,
            core=revised,
            case_ids=loads(latest.reference_case_ids_json, []),
            hook_ids=loads(latest.reference_hook_ids_json, []),
        )
