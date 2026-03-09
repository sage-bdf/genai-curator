# This deliverable is considered developed content as defined in contract between BDF parties.


"""Type definitions for the metadata correction pipeline."""

from pathlib import Path
from typing import Dict, TypeVar, Union

# Basic metadata value types
MetadataValue = Union[str, int, float, bool]
MetadataDict = Dict[str, MetadataValue]

# Generic type variables for node inputs/outputs
InputType = TypeVar("InputType")
OutputType = TypeVar("OutputType")

# Type aliases for common types
FilePath = Union[str, Path]
FileContent = str
FieldName = str
ErrorMessage = str

# Validation types
ValidationLevel = str  # One of: "strict", "lenient", "permissive"
ConstraintType = str  # One of: "required", "pattern", "range", "enum"

# Correction types
ConfidenceScore = float  # Between 0 and 1
CorrectionPriority = int  # Higher number = higher priority
