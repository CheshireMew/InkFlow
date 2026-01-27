"""
Pipelines Router

API endpoints for pipeline execution.
All business logic is delegated to the PipelineEngine.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.engine import get_engine
from core.exceptions import RecipeNotFoundError, PipelineNotFoundError, StepError

router = APIRouter()
logger = logging.getLogger("PipelineRouter")


class CreatePipelineRequest(BaseModel):
    recipe_id: str
    user_id: str = "anonymous"


class StepInputRequest(BaseModel):
    pipeline_id: str
    step_index: int
    inputs: Dict[str, Any]


@router.post("/create")
async def create_pipeline(request: CreatePipelineRequest):
    """Create a new pipeline from a recipe."""
    try:
        pipeline_id = get_engine().create_pipeline(request.recipe_id, request.user_id)
        return {"pipeline_id": pipeline_id}
    except RecipeNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    """Get pipeline status."""
    try:
        data = get_engine().get_pipeline(pipeline_id)
        # Flatten API response if needed, but engine returns dict compatible with frontend
        return data
    except PipelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_step(request: StepInputRequest):
    """Execute a specific step in a pipeline."""
    try:
        result = await get_engine().execute_step(request.pipeline_id, request.step_index, request.inputs)
        return result
    except PipelineNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StepError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error executing step: {e}")
        raise HTTPException(status_code=500, detail=str(e))
