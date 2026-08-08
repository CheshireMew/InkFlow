"""
Text Input Step

Handles user text input at the start of a pipeline.
"""

from steps.base import BaseStep, StepConfig, StepContext, StepResult
from steps.registry import register_step


@register_step
class TextInputStep(BaseStep):
    """
    User text input step.
    
    Config:
        placeholder: str - Placeholder text for UI
        max_length: int - Maximum text length (optional)
    """
    
    step_type = "text_input"
    
    async def execute(self, context: StepContext) -> StepResult:
        """
        Handle user input.
        Supports both simple 'user_input' (legacy) and multi-field forms.
        """
        # 1. Legacy single input mode
        if "user_input" in context.inputs:
            user_input = context.inputs["user_input"]
            if not user_input:
                return StepResult(success=False, error="No input provided")
            
            max_length = self.config.config.get("max_length")
            if max_length and len(user_input) > max_length:
                return StepResult(success=False, error=f"Input exceeds max length ({max_length})")
                
            return StepResult(success=True, data={"text": user_input, "user_input": user_input})
            
        # 2. Multi-field form mode
        fields = self.config.config.get("fields", [])
        if not fields:
            # Fallback if no fields configured but also no user_input parameter (shouldn't happen if frontend is correct)
            return StepResult(success=False, error="No fields configured and no input received")

        result_data = {}
        
        for field in fields:
            field_id = field.get("id")
            required = field.get("required", True)
            
            value = context.inputs.get(field_id)
            
            if required and not value:
                return StepResult(success=False, error=f"Field '{field.get('label', field_id)}' is required")
                
            result_data[field_id] = value
            
        # For backward compatibility, also key the first field as "text" if it looks like main content
        if "text" not in result_data and fields:
             result_data["text"] = list(result_data.values())[0]

        return StepResult(success=True, data=result_data)
