from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, JSON

class PipelineStepBase(SQLModel):
    """Base model for pipeline steps."""
    step_id: Optional[str] = None  # Original YAML ID
    type: str
    label: str
    status: str = "pending"
    config: Dict = Field(default={}, sa_column=Column(JSON))
    result: Optional[Any] = Field(default=None, sa_column=Column(JSON))
    index: int = 0

class PipelineStep(PipelineStepBase, table=True):
    """Database model for pipeline steps."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    pipeline_id: Optional[UUID] = Field(default=None, foreign_key="pipeline.id")
    
    pipeline: Optional["Pipeline"] = Relationship(back_populates="steps")


class PipelineBase(SQLModel):
    """Base model for pipelines."""
    recipe_id: str
    user_id: str = "anonymous"
    status: str = "in_progress"
    current_step: int = 0
    context: Dict = Field(default={"inputs": {}, "outputs": {}}, sa_column=Column(JSON))

class Pipeline(PipelineBase, table=True):
    """Database model for pipelines."""
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    
    steps: List[PipelineStep] = Relationship(
        back_populates="pipeline", 
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "PipelineStep.index"}
    )
