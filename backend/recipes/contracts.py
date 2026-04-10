from typing import Any, Literal

from pydantic import BaseModel, Field

from core.exceptions import RecipeValidationError
from recipes.loader import Recipe


CLIENT_STEP_TYPES = {"human_select"}
SERVER_STEP_TYPES = {"text_input", "llm_generate"}
STEP_STAGES = {
    "text_input": "input",
    "llm_generate": "generate",
    "human_select": "review",
}


class StepContract(BaseModel):
    id: str
    type: str
    label: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    run_mode: Literal["client", "server"]
    stage: Literal["input", "generate", "review"]
    auto_run: bool = False
    source_step: str | None = None


class RecipeContract(BaseModel):
    id: str
    name: str
    category: str = "other"
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    steps: list[StepContract]


def normalize_recipe(recipe: Recipe) -> RecipeContract:
    steps: list[StepContract] = []

    for index, raw_step in enumerate(recipe.steps):
        step_id = raw_step.id or f"step_{index}"
        step_type = raw_step.type

        if step_type == "export":
            raise RecipeValidationError(
                f"Recipe '{recipe.id}' still uses removed step type 'export'. "
                "Copy/export is now handled inside review steps."
            )

        if step_type in CLIENT_STEP_TYPES:
            run_mode: Literal["client", "server"] = "client"
        elif step_type in SERVER_STEP_TYPES:
            run_mode = "server"
        else:
            raise RecipeValidationError(
                f"Recipe '{recipe.id}' contains unsupported step type '{step_type}'"
            )

        stage = STEP_STAGES.get(step_type)
        if stage is None:
            raise RecipeValidationError(
                f"Recipe '{recipe.id}' cannot resolve stage for step type '{step_type}'"
            )

        source_step = _resolve_source_step(recipe.id, step_id, step_type, raw_step.config, steps)

        steps.append(
            StepContract(
                id=step_id,
                type=step_type,
                label=raw_step.label,
                config=raw_step.config,
                run_mode=run_mode,
                stage=stage,
                auto_run=step_type == "llm_generate",
                source_step=source_step,
            )
        )

    return RecipeContract(
        id=recipe.id,
        name=recipe.name,
        category=recipe.category,
        tags=recipe.tags,
        description=recipe.description,
        steps=steps,
    )


def _resolve_source_step(
    recipe_id: str,
    step_id: str,
    step_type: str,
    config: dict[str, Any],
    normalized_steps: list[StepContract],
) -> str | None:
    if step_type != "human_select":
        return None

    source_step = config.get("source_step")
    if source_step:
        return source_step

    if not normalized_steps:
        raise RecipeValidationError(
            f"Review step '{step_id}' in recipe '{recipe_id}' has no upstream generation step"
        )

    previous_step = normalized_steps[-1]
    if previous_step.type != "llm_generate":
        raise RecipeValidationError(
            f"Review step '{step_id}' in recipe '{recipe_id}' must follow an llm_generate step "
            "or declare config.source_step"
        )
    return previous_step.id
