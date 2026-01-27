"""
LLM Generate Step

Calls LLM API to generate content.
"""

import logging
from typing import List
from steps.base import BaseStep, StepContext, StepResult
from steps.registry import register_step
from services.llm_service import get_llm_service, LLMService

logger = logging.getLogger("LLMGenerate")


class DictObj:
    """Helper to allow dot notation access in string formatting."""
    def __init__(self, data):
        for k, v in data.items():
            if isinstance(v, dict):
                setattr(self, k, DictObj(v))
            else:
                setattr(self, k, v)
    
    def __getitem__(self, item):
        return getattr(self, item)


@register_step
class LLMGenerateStep(BaseStep):
    """
    LLM content generation step.
    
    Config:
        system_prompt: str
        prompt_template: str - Prompt template with {step_id.field} syntax
    """
    
    step_type = "llm_generate"
    
    async def execute(self, context: StepContext) -> StepResult:
        """Generate content using LLM."""
        service: LLMService = get_llm_service()
        
        system_prompt = self.config.config.get("system_prompt", "You are a helpful assistant.")
        prompt_template = self.config.config.get("prompt_template", "")
        
        # Build render context from inputs and previous outputs
        render_context = context.inputs.copy()
        
        # Add outputs to context, wrapped for dot notation access
        for step_id, output_data in context.outputs.items():
            if isinstance(output_data, dict):
                render_context[step_id] = DictObj(output_data)
            else:
                render_context[step_id] = output_data
        
        try:
            from jinja2 import Template, Environment
            import json
            
            # Create environment to register custom filters
            env = Environment()
            env.filters['from_json'] = json.loads
            
            template = env.from_string(prompt_template)
            user_prompt = template.render(**render_context)
        except Exception as e:
            return StepResult(success=False, error=f"Prompt formatting error (Jinja2): {e}")

        
        logger.info(f"Generating with prompt length: {len(user_prompt)}")
        
        # Detect model preference
        model_override = None
        # MAP: Friendly Name -> API Model ID
        MODEL_MAP = {
            "DeepSeek V3 (Fast)": "deepseek-chat",
            "DeepSeek R1 (Reasoning)": "deepseek-reasoner",
            "GPT-4o (Premium)": "gpt-4o",
        }
        
        # Search inputs for llm_model
        # render_context contains raw inputs + DictObj outputs
        for key, val in render_context.items():
            if isinstance(val, dict) and "llm_model" in val:
                found_name = val["llm_model"]
                model_override = MODEL_MAP.get(found_name)
                if model_override:
                    logger.info(f"🔀 Switching model to: {model_override} (User selected: {found_name})")
                    break
        
        try:
            output_format = self.config.config.get("output_format", "text")
            logger.info(f"DEBUG: Determined Output Format: '{output_format}'")
            
            if output_format == "json":
                # Single call expecting JSON structure
                content = await service.generate_content(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model_override
                )
                
                # Parse JSON
                import json
                import re
                
                # Try to find JSON array if wrapped in md code block
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    content_str = json_match.group(0)
                else:
                    content_str = content

                try:
                    parsed = json.loads(content_str)
                    if isinstance(parsed, list):
                        # Allow both strings and dicts in variants
                        variants = parsed
                    else:
                        variants = [str(parsed)]
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON output: {content}")
                    # Fallback: treat raw content as single variant
                    variants = [content]
                    
            else:
                # Default behavior: 3 variants via temperature sampling
                variants = await service.generate_variants(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    n=3,
                    model=model_override
                )
            
            return StepResult(success=True, data={"variants": variants, "awaiting_selection": True})
            
        except Exception as e:
            logger.error(f"LLM service error: {e}")
            return StepResult(success=False, error=f"LLM service error: {str(e)}")
