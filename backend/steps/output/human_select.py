"""Human Select Step - allows user to choose from generated variants."""

from steps.base import BaseStep, StepConfig, StepContext, StepResult
from steps.registry import register_step


@register_step  
class HumanSelectStep(BaseStep):
    """
    Human selection step.
    
    Presents generated variants to user for selection/editing.
    The selection is handled by the frontend UI.
    """
    
    step_type = "human_select"
    
    async def execute(self, context: StepContext) -> StepResult:
        """
        Present options for human selection.
        The actual selection comes from context.inputs["selected_index"]
        """
        # Get variants from previous step
        variants = []
        for output in context.outputs.values():
            if isinstance(output, dict) and "variants" in output:
                variants = output["variants"]
                break
        
        if not variants:
            return StepResult(success=False, error="No variants to select from")
        
        # Check if user has made a selection
        selected_idx = context.inputs.get("selected_index")
        edited_text = context.inputs.get("edited_text")
        
        if edited_text:
            # User edited the content
            return StepResult(
                success=True,
                data={
                    "content": edited_text,
                    "selected": [edited_text]
                }
            )
        
        # Check for multiple selections (New)
        selected_indices = context.inputs.get("selected_indices")
        if selected_indices is not None and isinstance(selected_indices, list):
            selected_variants = []
            final_content_parts = []
            
            for idx in selected_indices:
                if 0 <= idx < len(variants):
                    v = variants[idx]
                    selected_variants.append(v)
                    # For content, we only want the actual text, not the label object
                    if isinstance(v, dict):
                        final_content_parts.append(v.get("content", ""))
                    else:
                        final_content_parts.append(str(v))
            
            return StepResult(
                success=True,
                data={
                    "content": "\n\n".join(final_content_parts),
                    "selected": selected_variants
                }
            )

        # Legacy single selection
        if selected_idx is not None:
            if 0 <= selected_idx < len(variants):
                v = variants[selected_idx]
                content = v.get("content", "") if isinstance(v, dict) else str(v)
                return StepResult(
                    success=True,
                    data={
                        "content": content,
                        "selected": [v]
                    }
                )
        
        # Waiting for user selection
        return StepResult(
            success=True,
            data={"variants": variants, "awaiting_selection": True},
            needs_review=True
        )
