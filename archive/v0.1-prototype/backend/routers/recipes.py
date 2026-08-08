"""
Recipes Router

API endpoints for recipe management.
"""

from fastapi import APIRouter, HTTPException
from typing import List

from recipes.contracts import normalize_recipe
from recipes.loader import get_recipe_loader
from core.exceptions import RecipeNotFoundError

router = APIRouter()


@router.get("/", response_model=List[dict])
async def list_recipes():
    """List all available recipes."""
    loader = get_recipe_loader()
    recipes = loader.list_all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "tags": r.tags,
            "description": r.description,
            "step_count": len(r.steps)
        }
        for r in recipes
    ]


@router.get("/categories")
async def list_categories():
    """List all recipe categories."""
    loader = get_recipe_loader()
    return {"categories": loader.get_categories()}


@router.get("/{recipe_id}")
async def get_recipe(recipe_id: str):
    """Get a recipe by ID with full details."""
    loader = get_recipe_loader()
    try:
        recipe = loader.get(recipe_id)
        return normalize_recipe(recipe).model_dump()
    except RecipeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Recipe '{recipe_id}' not found")
