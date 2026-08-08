"""
InkFlow Step Base Class

All step types must inherit from this base class.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class StepConfig(BaseModel):
    """Configuration for a step instance."""
    type: str
    label: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)


class StepContext(BaseModel):
    """Context passed between steps in a pipeline."""
    pipeline_id: str
    user_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    
    def get_previous_output(self, step_id: str) -> Optional[Any]:
        """Get output from a previous step."""
        return self.outputs.get(step_id)


class StepResult(BaseModel):
    """Result returned by a step execution."""
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    needs_review: bool = False  # True if human review needed


class BaseStep(ABC):
    """
    Abstract base class for all step types.
    
    To create a new step:
    1. Create a file in steps/{category}/ (e.g., steps/llm/generate.py)
    2. Inherit from BaseStep
    3. Implement the execute() method
    4. The step will be auto-registered by the registry
    """
    
    # Unique step type identifier (e.g., "text_input", "llm_generate")
    step_type: str = ""
    
    def __init__(self, config: StepConfig):
        self.config = config
        self.label = config.label
    
    @abstractmethod
    async def execute(self, context: StepContext) -> StepResult:
        """
        Execute the step.
        
        Args:
            context: Pipeline context with inputs and previous outputs
            
        Returns:
            StepResult with success status and data
        """
        pass
    
    def validate_config(self) -> bool:
        """Optional: validate step configuration."""
        return True
