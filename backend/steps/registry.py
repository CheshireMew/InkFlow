"""
InkFlow Step Registry

Auto-discovers and registers all step types from the steps/ directory.
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Dict, Type

from .base import BaseStep, StepConfig

logger = logging.getLogger("StepRegistry")

# Global registry: step_type -> step_class
_registry: Dict[str, Type[BaseStep]] = {}


def register_step(step_class: Type[BaseStep]) -> Type[BaseStep]:
    """
    Decorator to register a step class.
    
    Usage:
        @register_step
        class TextInputStep(BaseStep):
            step_type = "text_input"
            ...
    """
    if not step_class.step_type:
        raise ValueError(f"Step class {step_class.__name__} must define step_type")
    
    _registry[step_class.step_type] = step_class
    logger.debug(f"📦 Registered step: {step_class.step_type}")
    return step_class


def get_step_class(step_type: str) -> Type[BaseStep]:
    """Get a registered step class by type."""
    if step_type not in _registry:
        from core.exceptions import StepNotFoundError
        raise StepNotFoundError(f"Step type '{step_type}' not registered", step_id=step_type)
    return _registry[step_type]


def create_step(config: StepConfig) -> BaseStep:
    """Create a step instance from config."""
    step_class = get_step_class(config.type)
    return step_class(config)


def list_step_types() -> list:
    """List all registered step types."""
    return list(_registry.keys())


def discover_steps():
    """
    Auto-discover all step modules in steps/{category}/ directories.
    
    This function should be called once at startup.
    """
    steps_dir = Path(__file__).parent
    
    # Categories to scan
    categories = ["input", "llm", "output"]
    
    for category in categories:
        category_dir = steps_dir / category
        if not category_dir.exists():
            continue
        
        # Import each module in the category
        for module_file in category_dir.glob("*.py"):
            if module_file.name.startswith("_"):
                continue
            
            module_name = f"steps.{category}.{module_file.stem}"
            try:
                importlib.import_module(module_name)
                logger.debug(f"📂 Loaded step module: {module_name}")
            except Exception as e:
                logger.error(f"❌ Failed to load {module_name}: {e}")
    
    logger.info(f"✅ Step registry: {len(_registry)} types registered")


# Auto-discover on import
# discover_steps()  # Comment out for now, call explicitly at startup
