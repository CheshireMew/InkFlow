import pytest

from core.exceptions import RecipeValidationError
from recipes.contracts import normalize_recipe
from recipes.loader import Recipe, RecipeStep


def test_normalize_recipe_builds_explicit_runtime_contract():
    recipe = Recipe(
        id="tweet_single",
        name="Tweet",
        steps=[
            RecipeStep(id="input", type="text_input", config={}),
            RecipeStep(id="generate", type="llm_generate", config={}),
            RecipeStep(id="review", type="human_select", config={}),
        ],
    )

    normalized = normalize_recipe(recipe)

    assert [step.run_mode for step in normalized.steps] == ["server", "server", "client"]
    assert [step.stage for step in normalized.steps] == ["input", "generate", "review"]
    assert normalized.steps[1].auto_run is True
    assert normalized.steps[2].source_step == "generate"


def test_normalize_recipe_rejects_removed_export_step():
    recipe = Recipe(
        id="legacy",
        name="Legacy",
        steps=[
            RecipeStep(id="input", type="text_input", config={}),
            RecipeStep(id="export", type="export", config={}),
        ],
    )

    with pytest.raises(RecipeValidationError):
        normalize_recipe(recipe)
