from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

from steps.registry import get_step_class
from steps.base import StepContext, StepConfig

router = APIRouter()
logger = logging.getLogger("ActionRouter")

class ExecuteActionRequest(BaseModel):
    tool: str  # e.g., "llm_generate"
    config: Dict[str, Any] = {}
    inputs: Dict[str, Any] = {}

@router.post("/run")
async def run_action(request: ExecuteActionRequest):
    """
    Stateless execution of a single tool/step.
    """
    try:
        # 1. Resolve Step Class
        step_cls = get_step_class(request.tool)
        if not step_cls:
            raise HTTPException(status_code=404, detail=f"Tool '{request.tool}' not found")
        
        # 2. Instantiate Step
        # ID is ephemeral here
        step_config = StepConfig(
            type=request.tool,
            label="Ephemeral Action",
            config=request.config
        )
        step_instance = step_cls(step_config)
        
        # 3. Create Ephemeral Context
        context = StepContext(
            pipeline_id="stateless",
            user_id="anonymous",
            current_step_index=0,
            inputs=request.inputs,
            outputs={} # No history needed for single atomic action
        )
        
        # 4. Execute
        logger.info(f"⚡ Executing stateless action: {request.tool}")
        result = await step_instance.execute(context)
        
        if not result.success:
             logger.warning(f"❌ Action failed: {result.error}")
             # We return 200 with error info so frontend handles it gracefully? 
             # Or 400? 200 is better for "business logic error".
        
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "meta": result.needs_review # or other flags
        }

    except Exception as e:
        logger.error(f"🔥 System Error in Action Runner: {e}")
        raise HTTPException(status_code=500, detail=str(e))
