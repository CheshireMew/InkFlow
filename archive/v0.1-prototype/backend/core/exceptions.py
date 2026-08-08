"""
InkFlow Exception Hierarchy

Provides structured exceptions for the application.
Adapted from Lumina project.
"""

from typing import Optional, Dict, Any


class InkFlowError(Exception):
    """Base exception for all InkFlow errors."""
    
    def __init__(
        self, 
        message: str, 
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        self.cause = cause
        
        if cause:
            self.__cause__ = cause
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for API responses."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details
        }
    
    def __str__(self):
        return f"[{self.code}] {self.message}"


# =============================================================================
# Recipe Errors
# =============================================================================

class RecipeError(InkFlowError):
    """Base class for recipe-related errors."""
    pass


class RecipeNotFoundError(RecipeError):
    """Recipe does not exist."""
    pass


class RecipeValidationError(RecipeError):
    """Recipe YAML format is invalid."""
    pass


# =============================================================================
# Step Errors
# =============================================================================

class StepError(InkFlowError):
    """Base class for step-related errors."""
    
    def __init__(self, message: str, step_id: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.step_id = step_id
        if step_id:
            self.details["step_id"] = step_id


class StepNotFoundError(StepError):
    """Step type not registered."""
    pass


class StepExecutionError(StepError):
    """Step failed during execution."""
    pass


# =============================================================================
# Pipeline Errors
# =============================================================================

class PipelineError(InkFlowError):
    """Base class for pipeline errors."""
    pass


class PipelineNotFoundError(PipelineError):
    """Pipeline session not found."""
    pass


# =============================================================================
# LLM Errors
# =============================================================================

class LLMError(InkFlowError):
    """Base class for LLM-related errors."""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timed out."""
    pass


class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded."""
    pass


# =============================================================================
# Knowledge Base Errors
# =============================================================================

class KnowledgeError(InkFlowError):
    """Base class for knowledge base errors."""
    pass


class DocumentParseError(KnowledgeError):
    """Failed to parse document (md/pdf)."""
    pass


class EmbeddingError(KnowledgeError):
    """Failed to generate embedding."""
    pass
