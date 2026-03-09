# This deliverable is considered developed content as defined in contract between BDF parties.


"""Core models for the metadata correction pipeline."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import pandas as pd
from pydantic import BaseModel, Field, field_validator


class ErrorType(str, Enum):
    """Types of validation errors."""

    SCHEMA = "schema"
    FORMAT = "format"
    VOCABULARY = "vocabulary"
    SEMANTIC = "semantic"
    CONTEXTUAL = "contextual"


class CorrectionMethod(str, Enum):
    """Types of correction methods."""

    FUZZY = "fuzzy"
    SEMANTIC = "semantic"
    INFERENCE = "inference"
    LLM = "llm"
    MANUAL = "manual"


class CorrectionAttempt(BaseModel):
    """Record of an attempted correction."""

    id: UUID = Field(default_factory=uuid4)
    method: CorrectionMethod = Field(..., description="Correction method used")
    row_idx: int = Field(..., description="Row index in DataFrame")
    column: str = Field(..., description="Column name")
    proposed_value: Any = Field(..., description="Suggested correction")
    confidence: float = Field(..., ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v


class CellError(BaseModel):
    """Error in a specific cell."""

    id: UUID = Field(default_factory=uuid4)
    row_idx: int = Field(..., description="Row index in DataFrame")
    column: str = Field(..., description="Column name")
    value: Any = Field(..., description="Invalid value")
    error_type: ErrorType = Field(..., description="Type of validation error")
    message: str = Field(..., description="Error description")
    correction_attempts: List[CorrectionAttempt] = Field(
        default_factory=list, description="History of correction attempts"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context for error"
    )


class SchemaField(BaseModel):
    """Schema field definition."""

    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Field data type")
    required: bool = Field(default=False)
    description: Optional[str] = None
    constraints: Dict[str, Any] = Field(default_factory=dict)
    valid_values: Optional[List[str]] = None
    examples: Optional[List[str]] = None


class Schema(BaseModel):
    """Metadata schema definition."""

    fields: List[SchemaField] = Field(..., description="Schema fields")
    version: str = Field(default="1.0.0")
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_field(self, name: str) -> Optional[SchemaField]:
        """Get field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None


class ValidationResult(BaseModel):
    """Result of schema validation."""

    is_valid: bool = Field(..., description="Overall validation result")
    errors: List[CellError] = Field(
        default_factory=list, description="Validation errors"
    )
    stats: Dict[str, Any] = Field(
        default_factory=dict, description="Validation statistics"
    )


class CorrectionResult(BaseModel):
    """Result of correction attempt."""

    error_id: UUID = Field(..., description="ID of error being corrected")
    attempt: CorrectionAttempt = Field(..., description="Correction attempt")
    success: bool = Field(..., description="Whether correction was successful")
    validation: Optional[ValidationResult] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PipelineState(BaseModel):
    """Current state of the correction pipeline."""

    metadata: pd.DataFrame = Field(
        ..., description="Current metadata state as DataFrame"
    )
    errors: List[CellError] = Field(
        default_factory=list, description="Current validation errors"
    )
    correction_history: List[CorrectionAttempt] = Field(
        default_factory=list, description="History of all corrections"
    )
    stats: Dict[str, Any] = Field(
        default_factory=dict, description="Pipeline statistics"
    )
    iteration: int = Field(default=0, description="Current pipeline iteration")

    class Config:
        arbitrary_types_allowed = True  # Allow pd.DataFrame
