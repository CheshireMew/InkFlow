"""
LLM Generate Step

Calls LLM API to generate content.
"""

import logging

from core.llm_generation import enforce_writing_contract, generate_variants, resolve_model_override
from core.templating import build_render_context, render_prompt_template
from core.writing_contract import build_writing_contract, compose_system_prompt
from steps.base import BaseStep, StepContext, StepResult
from steps.registry import register_step
from services.llm_service import get_llm_service

logger = logging.getLogger("LLMGenerate")


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
        service = get_llm_service()

        contract = build_writing_contract(self.config.config)
        system_prompt = compose_system_prompt(contract)
        prompt_template = self.config.config.get("prompt_template", "")
        output_format = self.config.config.get("output_format", "text")
        temperature = float(self.config.config.get("temperature", 0.7))
        render_context = build_render_context(context.inputs, context.outputs)

        try:
            user_prompt = render_prompt_template(prompt_template, render_context)
        except Exception as e:
            return StepResult(success=False, error=f"Prompt formatting error (Jinja2): {e}")

        logger.info(f"Generating with prompt length: {len(user_prompt)}")
        model_override = resolve_model_override(render_context)

        try:
            logger.info(f"DEBUG: Determined Output Format: '{output_format}'")
            variants = await generate_variants(
                service=service,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_format=output_format,
                temperature=temperature,
                model_override=model_override,
            )
            processed_variants = await enforce_writing_contract(
                variants=variants,
                contract=contract,
                service=service,
                system_prompt=system_prompt,
                model_override=model_override,
            )

            return StepResult(success=True, data={"variants": processed_variants, "awaiting_selection": True})

        except Exception as e:
            logger.error(f"LLM service error: {e}")
            return StepResult(success=False, error=f"LLM service error: {str(e)}")
