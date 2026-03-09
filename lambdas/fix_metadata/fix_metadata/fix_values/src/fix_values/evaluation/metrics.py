# This deliverable is considered developed content as defined in contract between BDF parties.


"""Evaluation metrics for metadata correction pipeline."""

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

from fix_values.pipeline.core.models import CorrectionAttempt, CorrectionMethod


@dataclass
class StageMetrics:
    """Metrics for a specific pipeline stage."""

    corrections: int  # Number of corrections attempted
    correction_accuracy: float  # Accuracy of corrections made
    correction_rate: float  # Percent of errors with correction attempts


@dataclass
class FieldMetrics:
    """Metrics for a single field."""

    base_accuracy: float  # Accuracy before corrections
    corrections: int  # Number of corrections made
    correction_accuracy: float  # Accuracy of corrections made
    correction_rate: float  # Percent of errors with correction attempts
    stage_metrics: Dict[CorrectionMethod, StageMetrics]  # Per-stage metrics


@dataclass
class EvaluationMetrics:
    """Overall evaluation metrics."""

    base_accuracy: float  # Accuracy before corrections
    total_corrections: int  # Total number of corrections made
    total_errors: int  # Total number of errors in raw data
    correction_accuracy: float  # Overall accuracy of corrections
    correction_rate: float  # Overall percent of errors with correction attempts
    stage_metrics: Dict[CorrectionMethod, StageMetrics]  # Per-stage metrics
    field_metrics: Dict[str, FieldMetrics]  # Per-field metrics
    execution_time: float  # Total execution time


def calculate_stage_metrics(
    ground_truth: pd.Series,
    predictions: pd.Series,
    stage_corrections: List[CorrectionAttempt],
    needs_correction: pd.Series,
) -> StageMetrics:
    """Calculate metrics for a specific pipeline stage."""
    if not stage_corrections:
        return StageMetrics(corrections=0, correction_accuracy=0.0, correction_rate=0.0)

    # Get rows where this stage made corrections
    corrected_indices = [c.row_idx for c in stage_corrections]
    stage_mask = pd.Series(False, index=ground_truth.index)
    stage_mask[corrected_indices] = True

    # Calculate metrics for this stage's corrections
    if len(corrected_indices) > 0:
        # Count successful corrections
        fixed_correctly = (ground_truth == predictions) & stage_mask & needs_correction
        correction_accuracy = fixed_correctly.sum() / len(corrected_indices)
        correction_rate = (
            len(corrected_indices) / needs_correction.sum()
            if needs_correction.sum() > 0
            else 0.0
        )
    else:
        correction_accuracy = 0.0
        correction_rate = 0.0

    return StageMetrics(
        corrections=len(stage_corrections),
        correction_accuracy=correction_accuracy,
        correction_rate=correction_rate,
    )


def calculate_field_metrics(
    ground_truth: pd.Series,
    predictions: pd.Series,
    input_values: pd.Series,
    errors: pd.Series,
    correction_history: Optional[List[CorrectionAttempt]] = None,
) -> FieldMetrics:
    """Calculate metrics for a single field."""
    # Calculate base accuracy (before corrections)
    base_accuracy = (input_values == ground_truth).mean()

    # Count corrections and calculate correction rate
    needs_correction = ground_truth != input_values
    num_errors = needs_correction.sum()
    num_corrections = ((predictions != input_values) & needs_correction).sum()
    correction_rate = num_corrections / num_errors if num_errors > 0 else 0.0

    # Calculate correction accuracy
    if num_corrections > 0:
        fixed_correctly = (ground_truth == predictions) & needs_correction
        correction_accuracy = fixed_correctly.sum() / num_corrections
    else:
        correction_accuracy = 1.0  # No corrections needed

    # Calculate stage-specific metrics
    stage_metrics = {}
    if correction_history:
        # Group corrections by method
        corrections_by_method = {}
        for method in CorrectionMethod:
            corrections_by_method[method] = [
                c for c in correction_history if c.method == method
            ]

        # Calculate metrics for each stage
        for method in CorrectionMethod:
            stage_metrics[method] = calculate_stage_metrics(
                ground_truth,
                predictions,
                corrections_by_method[method],
                needs_correction,
            )
    else:
        # Initialize empty metrics for each stage
        stage_metrics = {
            method: StageMetrics(
                corrections=0, correction_accuracy=0.0, correction_rate=0.0
            )
            for method in CorrectionMethod
        }

    return FieldMetrics(
        base_accuracy=base_accuracy,
        corrections=num_corrections,
        correction_accuracy=correction_accuracy,
        correction_rate=correction_rate,
        stage_metrics=stage_metrics,
    )


def calculate_overall_metrics(
    ground_truth_df: pd.DataFrame,
    predictions_df: pd.DataFrame,
    input_df: pd.DataFrame,
    confidence_df: pd.DataFrame,
    error_df: pd.DataFrame,
    correction_history: List[CorrectionAttempt],
    execution_time: float,
    ignore_fields: Optional[List[str]] = None,
) -> EvaluationMetrics:
    """Calculate overall evaluation metrics."""
    ignore_fields = ignore_fields or []

    # Create case-insensitive column mappings
    gt_columns = {col.lower(): col for col in ground_truth_df.columns}
    input_columns = {col.lower(): col for col in input_df.columns}
    pred_columns = {col.lower(): col for col in predictions_df.columns}
    error_columns = {col.lower(): col for col in error_df.columns}

    # Get all unique columns from both ground truth and input, excluding 'name' and ignored fields
    all_columns_lower = set(gt_columns.keys()).union(set(input_columns.keys()))
    all_columns_lower = all_columns_lower.difference(
        set(["name"])
    )  # Remove 'name' column
    all_columns_lower = all_columns_lower.difference(
        set(col.lower() for col in ignore_fields)
    )  # Remove ignored fields

    # Map back to original column names, preferring ground truth names if available
    all_columns = []
    for col_lower in all_columns_lower:
        if col_lower in gt_columns:
            all_columns.append(gt_columns[col_lower])
        else:
            all_columns.append(input_columns[col_lower])

    # Log all columns that will be included
    logger.info(f"Including the following columns: {sorted(all_columns)}")

    # Match rows between files using filename and create aligned DataFrames
    common_files = set(input_df["name"]).intersection(set(ground_truth_df["name"]))

    # Create aligned DataFrames using name as index
    input_aligned = input_df[input_df["name"].isin(common_files)].set_index("name")
    gt_aligned = ground_truth_df[ground_truth_df["name"].isin(common_files)].set_index(
        "name"
    )
    predictions_aligned = predictions_df[
        predictions_df["name"].isin(common_files)
    ].set_index("name")
    error_aligned = error_df[error_df["name"].isin(common_files)].set_index("name")

    # Sort all DataFrames by index (name) to ensure alignment
    input_aligned.sort_index(inplace=True)
    gt_aligned.sort_index(inplace=True)
    predictions_aligned.sort_index(inplace=True)
    error_aligned.sort_index(inplace=True)

    # Calculate field-level metrics
    field_metrics = {}
    for field in all_columns:
        field_lower = field.lower()

        # Get corresponding column names in each DataFrame
        gt_field = gt_columns.get(field_lower)
        input_field = input_columns.get(field_lower)
        pred_field = pred_columns.get(field_lower)
        error_field = error_columns.get(field_lower)

        # Filter correction history for this field
        field_corrections = [
            c for c in correction_history if c.column.lower() == field_lower
        ]

        # Skip if no corrections were made for this field
        if not field_corrections:
            continue

        logger.info(f"Calculating Field Metrics: {field}")

        # Create placeholder series for missing fields
        gt_series = (
            gt_aligned[gt_field] if gt_field else pd.Series(index=input_aligned.index)
        )
        input_series = (
            input_aligned[input_field]
            if input_field
            else pd.Series(index=input_aligned.index)
        )
        pred_series = (
            predictions_aligned[pred_field]
            if pred_field
            else pd.Series(index=input_aligned.index)
        )
        error_series = (
            error_aligned[error_field]
            if error_field
            else pd.Series(False, index=input_aligned.index)
        )

        metrics = calculate_field_metrics(
            gt_series, pred_series, input_series, error_series, field_corrections
        )
        field_metrics[field] = metrics

    # Calculate overall metrics using all fields with corrections
    total_corrections = sum(m.corrections for m in field_metrics.values())

    # Calculate total errors and base accuracy only for fields that exist in both DataFrames
    common_columns = [
        col
        for col in all_columns
        if col.lower() in gt_columns and col.lower() in input_columns
    ]
    total_errors = sum(
        1
        for field in common_columns
        for name in gt_aligned.index
        if gt_aligned[field].iloc[gt_aligned.index.get_loc(name)]
        != input_aligned[input_columns[field.lower()]].iloc[
            input_aligned.index.get_loc(name)
        ]
    )

    total_cells = len(gt_aligned) * len(common_columns)
    correct_cells = sum(
        1
        for field in common_columns
        for name in gt_aligned.index
        if input_aligned[input_columns[field.lower()]].iloc[
            input_aligned.index.get_loc(name)
        ]
        == gt_aligned[field].iloc[gt_aligned.index.get_loc(name)]
    )
    base_accuracy = correct_cells / total_cells if total_cells > 0 else 0.0

    # Calculate overall correction accuracy and rate
    if total_corrections > 0:
        # Count correct fixes only for fields that exist in ground truth
        correct_fixes = 0
        for field in field_metrics:
            field_lower = field.lower()
            if field_lower in gt_columns and field_lower in pred_columns:
                gt_field = gt_columns[field_lower]
                pred_field = pred_columns[field_lower]
                input_field = input_columns.get(field_lower)

                for name in gt_aligned.index:
                    if predictions_aligned[pred_field].iloc[
                        predictions_aligned.index.get_loc(name)
                    ] == gt_aligned[gt_field].iloc[gt_aligned.index.get_loc(name)] and (
                        not input_field
                        or input_aligned[input_field].iloc[
                            input_aligned.index.get_loc(name)
                        ]
                        != gt_aligned[gt_field].iloc[gt_aligned.index.get_loc(name)]
                    ):
                        correct_fixes += 1

        correction_accuracy = correct_fixes / total_corrections
    else:
        correction_accuracy = 1.0  # No corrections needed

    correction_rate = total_corrections / total_errors if total_errors > 0 else 0.0

    # Calculate overall stage metrics
    stage_metrics = {}
    for method in CorrectionMethod:
        # Include all corrections for this method
        stage_corrections = [c for c in correction_history if c.method == method]
        total_stage_corrections = len(stage_corrections)

        if total_stage_corrections > 0:
            # Count correct fixes only for fields that exist in ground truth
            correct_stage_fixes = 0
            for c in stage_corrections:
                field_lower = c.column.lower()
                if field_lower in gt_columns and field_lower in pred_columns:
                    gt_field = gt_columns[field_lower]
                    pred_field = pred_columns[field_lower]
                    row_name = input_df.iloc[c.row_idx]["name"]

                    if (
                        predictions_aligned[pred_field].loc[row_name]
                        == gt_aligned[gt_field].loc[row_name]
                    ):
                        correct_stage_fixes += 1

            stage_correction_accuracy = correct_stage_fixes / total_stage_corrections
            stage_correction_rate = (
                total_stage_corrections / total_errors if total_errors > 0 else 0.0
            )
        else:
            stage_correction_accuracy = 0.0
            stage_correction_rate = 0.0

        stage_metrics[method] = StageMetrics(
            corrections=total_stage_corrections,
            correction_accuracy=stage_correction_accuracy,
            correction_rate=stage_correction_rate,
        )

    return EvaluationMetrics(
        base_accuracy=base_accuracy,
        total_corrections=total_corrections,
        total_errors=total_errors,
        correction_accuracy=correction_accuracy,
        correction_rate=correction_rate,
        stage_metrics=stage_metrics,
        field_metrics=field_metrics,
        execution_time=execution_time,
    )
