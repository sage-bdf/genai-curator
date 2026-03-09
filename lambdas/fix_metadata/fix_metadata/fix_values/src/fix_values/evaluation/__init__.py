# This deliverable is considered developed content as defined in contract between BDF parties.


"""Evaluation package for metadata correction pipeline."""

from .evaluator import EvaluationResult, PipelineEvaluator
from .metrics import (
    EvaluationMetrics,
    FieldMetrics,
    calculate_field_metrics,
    calculate_overall_metrics,
)

__all__ = [
    # Evaluator
    "EvaluationResult",
    "PipelineEvaluator",
    # Metrics
    "EvaluationMetrics",
    "FieldMetrics",
    "calculate_field_metrics",
    "calculate_overall_metrics",
]
