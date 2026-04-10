"""
InkFlow Tool Registry

Auto-discovers and registers all tool types from the tools/ directory.
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Dict, Type

from .base import BaseStep, StepConfig

logger = logging.getLogger("ToolRegistry")

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
    logger.debug(f"📦 Registered tool: {step_class.step_type}")
    return step_class


def get_step_class(step_type: str) -> Type[BaseStep]:
    """Get a registered step class by type."""
    if step_type not in _registry:
        from core.exceptions import StepNotFoundError
        raise StepNotFoundError(f"Tool type '{step_type}' not registered", step_id=step_type)
    return _registry[step_type]


def create_step(config: StepConfig) -> BaseStep:
    """Create a step instance from config."""
    step_class = get_step_class(config.type)
    return step_class(config)


def list_step_types() -> list:
    """List all registered tool types."""
    return list(_registry.keys())


def discover_steps():
    """
    Auto-discover all tool modules in the flat tools/ directory.
    
    This function should be called once at startup.
    """
    tools_dir = Path(__file__).parent
    
    # Scan all .py files in tools/ (flat structure)
    for module_file in tools_dir.glob("*.py"):
        # Skip __init__, base, registry
        if module_file.name.startswith("_") or module_file.stem in ["base", "registry"]:
            continue
        
        module_name = f"steps.{module_file.stem}"
        try:
            importlib.import_module(module_name)
            logger.debug(f"📂 Loaded tool module: {module_name}")
        except Exception as e:
            logger.error(f"❌ Failed to load {module_name}: {e}")
    
    logger.info(f"✅ Tool registry: {len(_registry)} types registered")

