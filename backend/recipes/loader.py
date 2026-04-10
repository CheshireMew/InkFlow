"""
InkFlow Recipe Loader

Loads and manages recipe definitions from YAML files.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from pydantic import BaseModel, Field
from core.exceptions import RecipeNotFoundError, RecipeValidationError

logger = logging.getLogger("RecipeLoader")


class RecipeStep(BaseModel):
    """Step definition within a recipe."""
    id: Optional[str] = None
    type: str
    label: str = ""
    config: dict = Field(default_factory=dict)


class Recipe(BaseModel):
    """Recipe definition."""
    id: str
    name: str
    category: str = "other"
    tags: List[str] = Field(default_factory=list)
    steps: List[RecipeStep]
    description: str = ""


class RecipeLoader:
    """
    Loads and manages recipes from YAML files.
    
    Usage:
        loader = RecipeLoader("./recipes")
        recipe = loader.get("tweet_single")
    """
    
    def __init__(self, recipes_dir: str | Path):
        self.recipes_dir = Path(recipes_dir)
        self._cache: Dict[str, Recipe] = {}
    
    def load_all(self) -> Dict[str, Recipe]:
        """Load all recipes from the recipes directory."""
        self._cache.clear()
        
        if not self.recipes_dir.exists():
            logger.warning(f"⚠️ Recipes directory not found: {self.recipes_dir}")
            return {}
        
        # Scan all subdirectories
        for yaml_file in self.recipes_dir.rglob("*.yaml"):
            try:
                recipe = self._load_file(yaml_file)
                self._cache[recipe.id] = recipe
                logger.debug(f"📜 Loaded recipe: {recipe.id}")
            except Exception as e:
                logger.error(f"❌ Failed to load {yaml_file}: {e}")
        
        logger.info(f"✅ Loaded {len(self._cache)} recipes")
        return self._cache
    
    def _load_file(self, path: Path) -> Recipe:
        """Load a single recipe file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        if not data:
            raise RecipeValidationError(f"Empty recipe file: {path}")
        
        # Validate required fields
        if "id" not in data:
            raise RecipeValidationError(f"Missing 'id' in recipe: {path}")
        if "name" not in data:
            raise RecipeValidationError(f"Missing 'name' in recipe: {path}")
        if "steps" not in data:
            raise RecipeValidationError(f"Missing 'steps' in recipe: {path}")
        
        # Parse steps
        steps = [RecipeStep(**s) for s in data["steps"]]
        
        return Recipe(
            id=data["id"],
            name=data["name"],
            category=data.get("category", "other"),
            tags=data.get("tags", []),
            steps=steps,
            description=data.get("description", "")
        )
    
    def get(self, recipe_id: str) -> Recipe:
        """Get a recipe by ID."""
        if recipe_id not in self._cache:
            # Try reloading all if not found
            self.load_all()
            
        if recipe_id not in self._cache:
            raise RecipeNotFoundError(f"Recipe not found: {recipe_id}")
        return self._cache[recipe_id]

    def reload(self):
         """Force reload all recipes from disk."""
         self.load_all()
    
    def list_all(self) -> List[Recipe]:
        """List all loaded recipes."""
        return list(self._cache.values())
    
    def list_by_category(self, category: str) -> List[Recipe]:
        """List recipes in a category."""
        return [r for r in self._cache.values() if r.category == category]
    
    def get_categories(self) -> List[str]:
        """Get all unique categories."""
        return list(set(r.category for r in self._cache.values()))


# Global loader instance
_loader: Optional[RecipeLoader] = None


def get_recipe_loader() -> RecipeLoader:
    """Get the global recipe loader."""
    global _loader
    if _loader is None:
        # Default path - will be configured at startup
        _loader = RecipeLoader(Path(__file__).parent.parent.parent / "recipes")
    return _loader


def init_recipe_loader(recipes_dir: str | Path):
    """Initialize the recipe loader with a custom path."""
    global _loader
    _loader = RecipeLoader(recipes_dir)
    _loader.load_all()
