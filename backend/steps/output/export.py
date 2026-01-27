"""
Export Step

Exports the final content in various formats.
"""

from typing import Optional
from steps.base import BaseStep, StepConfig, StepContext, StepResult
from steps.registry import register_step


@register_step
class ExportStep(BaseStep):
    """
    Content export step.
    
    Handles final output - copying to clipboard, saving to file, etc.
    The actual export action is triggered by the frontend.
    """
    
    step_type = "export"
    
    async def execute(self, context: StepContext) -> StepResult:
        """
        Prepare content for export.
        The frontend will handle the actual export action.
        """
        # Find the final content from previous steps
        final_content = self._find_final_content(context)
        
        if not final_content:
            return StepResult(
                success=False,
                error="No content to export"
            )
        
        return StepResult(
            success=True,
            data={
                "content": final_content,
                "export_options": ["clipboard", "file", "publish"]
            }
        )
    
    def _find_final_content(self, context: StepContext) -> Optional[str]:
        """Find the final content from pipeline outputs."""
        # Check for selected variant
        if "selected_content" in context.inputs:
            return context.inputs["selected_content"]
        
        # Check outputs from previous steps
        for step_id, output in reversed(list(context.outputs.items())):
            if isinstance(output, dict):
                # Prefer selected variant
                if "selected" in output:
                    return output["selected"]
                # Or first variant
                if "variants" in output and output["variants"]:
                    return output["variants"][0]
                # Or raw text
                if "text" in output:
                    return output["text"]
        
        return None
