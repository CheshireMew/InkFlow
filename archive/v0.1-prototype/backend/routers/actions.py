import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.exceptions import InkFlowError, LLMError, LLMRateLimitError, LLMTimeoutError, StepNotFoundError
from steps.registry import get_step_class
from steps.base import StepContext, StepConfig

router = APIRouter()
logger = logging.getLogger("ActionRouter")

class ExecuteActionRequest(BaseModel):
    tool: str  # e.g., "llm_generate"
    config: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)

@router.post("/run")
async def run_action(request: ExecuteActionRequest):
    """
    Stateless execution of a single tool/step.
    """
    try:
        step_cls = get_step_class(request.tool)

        step_config = StepConfig(
            type=request.tool,
            label="Ephemeral Action",
            config=request.config
        )
        step_instance = step_cls(step_config)

        if not step_instance.validate_config():
            raise HTTPException(status_code=400, detail="Invalid step configuration")

        context = StepContext(
            pipeline_id="stateless",
            user_id="anonymous",
            inputs=request.inputs,
            outputs={}
        )

        logger.info(f"⚡ Executing stateless action: {request.tool}")
        result = await step_instance.execute(context)

        if not result.success:
            logger.warning(f"❌ Action failed: {result.error}")

        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "meta": {"needs_review": result.needs_review}
        }

    except HTTPException:
        raise
    except StepNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.to_dict()) from exc
    except InkFlowError as exc:
        logger.warning(f"Action rejected: {exc}")
        raise HTTPException(status_code=_error_status_code(exc), detail=exc.to_dict()) from exc
    except Exception as e:
        logger.exception(f"🔥 System Error in Action Runner: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "InternalServerError", "message": "Internal server error"}
        ) from e


def _error_status_code(error: InkFlowError) -> int:
    if isinstance(error, LLMTimeoutError):
        return 504
    if isinstance(error, LLMRateLimitError):
        return 429
    if isinstance(error, LLMError):
        return 502
    return 400
