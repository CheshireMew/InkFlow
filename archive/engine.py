"""
InkFlow PipelineEngine (SQLModel Version)

Manages pipeline lifecycle using SQLite persistence.
"""

import logging
import uuid
from uuid import UUID
from typing import Dict, Any, Optional, List
from threading import Lock

from sqlmodel import Session, select
from db.database import engine as db_engine, create_db_and_tables
from models.pipeline import Pipeline, PipelineStep

from recipes.loader import get_recipe_loader
from steps import create_step, StepConfig, StepContext
from core.exceptions import RecipeNotFoundError, StepError, PipelineNotFoundError

logger = logging.getLogger("PipelineEngine")


class PipelineEngine:
    """
    Manages the lifecycle and execution of pipelines using SQLModel persistence.
    """
    
    def __init__(self):
        # Ensure tables exist on startup
        create_db_and_tables()
        # Simple lock to prevent concurrent writes on same pipeline (SQLite limitation mostly)
        self._lock = Lock()
        # Recover recovered steps
        self._recover_crashed_steps()

    def _recover_crashed_steps(self):
        """Reset steps left in 'running' state due to server crash."""
        try:
            with Session(db_engine) as session:
                statement = select(PipelineStep).where(PipelineStep.status == "running")
                results = session.exec(statement).all()
                count = 0
                for step in results:
                    step.status = "failed"
                    step.result = {"error": "Server restarted during execution"}
                    session.add(step)
                    count += 1
                
                if count > 0:
                    session.commit()
                    logger.warning(f"🔧 Recovered {count} crashed steps (reset to failed)")
        except Exception as e:
            logger.error(f"Failed to recover crashed steps: {e}")

    def create_pipeline(self, recipe_id: str, user_id: str = "anonymous") -> str:
        """Create a new pipeline instance in DB."""
        loader = get_recipe_loader()
        try:
            recipe = loader.get(recipe_id)
        except RecipeNotFoundError:
            raise RecipeNotFoundError(f"Recipe '{recipe_id}' not found")
        
        with Session(db_engine) as session:
            # Create Pipeline Record
            pipeline = Pipeline(
                recipe_id=recipe_id,
                user_id=user_id,
                status="in_progress",
                current_step=0,
                context={"inputs": {}, "outputs": {}}
            )
            session.add(pipeline)
            session.commit() # Commit to get ID
            session.refresh(pipeline)
            
            # Create Step Records
            for i, s in enumerate(recipe.steps):
                step = PipelineStep(
                    pipeline_id=pipeline.id,
                    step_id=s.id,     # YAML ID
                    type=s.type,
                    label=s.label,
                    status="pending",
                    config=s.config, # JSON
                    result=None,
                    index=i
                )
                session.add(step)
            
            session.commit()
            logger.info(f"✨ Pipeline created in DB: {pipeline.id}")
            return str(pipeline.id)

    def get_pipeline(self, pipeline_id: str) -> Dict[str, Any]:
        """Get pipeline state from DB."""
        with Session(db_engine) as session:
            try:
                p_uuid = UUID(pipeline_id)
            except ValueError:
                raise PipelineNotFoundError(f"Invalid UUID string: {pipeline_id}")

            pipeline = session.get(Pipeline, p_uuid)
            if not pipeline:
                raise PipelineNotFoundError(f"Pipeline {pipeline_id} not found")
            
            # Convert to dict structure expected by frontend
            # Sort steps by index
            steps = sorted(pipeline.steps, key=lambda x: x.index)
            
            pipeline_data = {
                "id": str(pipeline.id),
                "recipe_id": pipeline.recipe_id,
                "status": pipeline.status,
                "current_step": pipeline.current_step,
                "steps": [
                    {
                        "index": s.index,
                        "id": s.step_id,
                        "type": s.type,
                        "label": s.label,
                        "status": s.status,
                        "config": s.config, # Already dict
                        "result": s.result, # Already dict or None
                    }
                    for s in steps
                ],
                "context": pipeline.context
            }
            
            # Inject dependencies (Client-side view logic)
            self._inject_dependencies(pipeline_data)
            
            return pipeline_data

    def _inject_dependencies(self, pipeline_data: Dict[str, Any]):
        """Inject outputs into pending steps."""
        for step in pipeline_data["steps"]:
            # Inject for COMPLETED steps too, so they can render the list
            if step["type"] == "human_select":
                config = step.get("config", {})
                source_id = config.get("source_step")
                
                if source_id:
                    # Find source result in pipeline data
                    # Note: source_id refers to step_id (YAML ID)
                    for s in pipeline_data["steps"]:
                        if s["id"] == source_id and s["status"] == "completed":
                            if "config" not in step: step["config"] = {}
                            # Inject variants
                            step["config"]["variants"] = s["result"].get("variants")
                            break

    async def execute_step(self, pipeline_id: str, step_index: int, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a step updating DB state."""
        # Convert string ID to UUID once here to catch errors early
        try:
            p_uuid = UUID(pipeline_id)
        except ValueError:
            raise PipelineNotFoundError(f"Invalid UUID string: {pipeline_id}")

        # Variables to hold data extracted from session
        step_type = None
        step_config_data = None
        step_record_id = None
        current_pipeline_status = None
        
        with self._lock:  # Simple lock for thread safety
             with Session(db_engine) as session:
                pipeline = session.get(Pipeline, p_uuid)
                if not pipeline:
                    raise PipelineNotFoundError(f"Pipeline {pipeline_id} not found")
                
                # Sort steps
                steps = sorted(pipeline.steps, key=lambda x: x.index)
                
                if step_index >= len(steps):
                    raise StepError("Step index out of bounds")
                
                # Check sequence logic
                step_record = steps[step_index]

                # === HOT CONFIG RELOAD ===
                # Force reload recipe from disk to support "Edit YAML -> Run" workflow
                try:
                    loader = get_recipe_loader()
                    loader.reload() 
                    fresh_recipe = loader.get(pipeline.recipe_id)
                    if step_index < len(fresh_recipe.steps):
                         fresh_step_def = fresh_recipe.steps[step_index]
                         step_record.config = fresh_step_def.config
                         session.add(step_record)
                         logger.info(f"🔥 Hot Loaded fresh config for step {step_index} from YAML")
                except Exception as e:
                    logger.warning(f"⚠️ Hot Config Reload failed: {e}")
                # ==========================
                
                if step_index != pipeline.current_step:
                    # Rerun logic
                    if step_record.status == "completed" or step_index < pipeline.current_step:
                        self._reset_from_step(session, pipeline, steps, step_index)
                        # We must commit here to persist the reset before running
                        session.commit()
                        session.refresh(pipeline)
                        # Re-fetch steps after reset
                        steps = sorted(pipeline.steps, key=lambda x: x.index)
                        step_record = steps[step_index]
                    else:
                        raise StepError(f"Cannot execute step {step_index}. Current is {pipeline.current_step}")

                # Prepare context
                context = StepContext(
                    pipeline_id=str(pipeline.id),
                    user_id=pipeline.user_id,
                    current_step_index=step_index,
                    inputs=inputs,
                    outputs=pipeline.context.get("outputs", {})
                )
                
                # Mark running
                step_record.status = "running"
                session.add(step_record)
                session.commit() 
                session.refresh(step_record)
                
                # EXTRACT DATA before session closes
                step_type = step_record.type
                step_label = step_record.label
                step_inner_config = step_record.config.copy()
                step_record_id = step_record.id
                current_pipeline_status = pipeline.status
         
        # Execute outside lock to allow other reads
        try:
            step_config = StepConfig(
                type=step_type,
                label=step_label,
                config=step_inner_config
            )
            step_executor = create_step(step_config)
            
            result = await step_executor.execute(context)
            
            # Write result (New session)
            with Session(db_engine) as session:
                pipeline = session.get(Pipeline, p_uuid)
                step_record = session.get(PipelineStep, step_record_id)
                
                if not step_record:
                     raise StepError("Step record disappeared during execution")

                step_record.status = "completed" if result.success else "failed"
                
                # Persist result or error
                if result.success:
                    step_record.result = result.data
                else:
                    # Ensure error is saved as data for frontend to see
                    step_record.result = {"error": result.error or "Unknown error"}
                    
                session.add(step_record)
                
                if result.success:
                    # Update outputs
                    if pipeline:
                        outputs = pipeline.context.get("outputs", {}).copy()
                        step_id = step_record.step_id or f"step_{step_index}"
                        outputs[step_id] = result.data
                        
                        # Update context
                        pipeline.context = {"inputs": pipeline.context.get("inputs"), "outputs": outputs}
                        session.add(pipeline)
                        
                        # Advance
                        if not result.needs_review:
                            pipeline.current_step += 1
                            # Check completion
                            total_steps = len(pipeline.steps)
                            if pipeline.current_step >= total_steps:
                                 pipeline.status = "completed"
                            session.add(pipeline)
                
                session.commit()
                # Refresh to return latest status
                if pipeline:
                     session.refresh(pipeline)
                     current_pipeline_status = pipeline.status
                     next_step_idx = pipeline.current_step
                else:
                     next_step_idx = step_index
                
            return {
                "success": result.success,
                "data": result.data if result.success else {"error": result.error or "Unknown error"},
                "pipeline_status": current_pipeline_status if result.success else "in_progress",
                "next_step": next_step_idx if result.success else step_index
            }

        except Exception as e:
            # Mark failed
            with Session(db_engine) as session:
                if step_record_id:
                    step_m = session.get(PipelineStep, step_record_id)
                    if step_m:
                        step_m.status = "failed"
                        step_m.result = {"error": str(e)}
                        session.add(step_m)
                        session.commit()
            logger.error(f"Execution failed: {e}")
            
            # Return failure response instead of crashing
            return {
                "success": False,
                "data": {"error": str(e)},
                "pipeline_status": "in_progress", # Continue allowing retries? Or failed?
                "next_step": step_index
            }

    def _reset_from_step(self, session: Session, pipeline: Pipeline, steps: List[PipelineStep], step_index: int):
        """Reset DB state from step index."""
        logger.info(f"🔄 Rolling back pipeline {pipeline.id} to step {step_index}")
        
        for i in range(step_index, len(steps)):
            steps[i].status = "pending"
            steps[i].result = None
            session.add(steps[i])
            
        pipeline.current_step = step_index
        pipeline.status = "in_progress"
        session.add(pipeline)


# Global Engine Instance
_engine = PipelineEngine()

def get_engine() -> PipelineEngine:
    return _engine
