# This deliverable is considered developed content as defined in contract between BDF parties.


"""Evaluator for metadata correction pipeline."""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import BaseModel

# Prevent silent downcasting in pandas
pd.set_option("future.no_silent_downcasting", True)

from fix_values.evaluation.metrics import (
    CorrectionMethod,
    EvaluationMetrics,
    calculate_overall_metrics,
)
from fix_values.pipeline import MetadataCorrectionConfig
from fix_values.pipeline.pipeline import MetadataCorrectionPipeline


class BatchEvaluationMetrics(BaseModel):
    """Overall metrics across all files."""

    total_files: int
    base_accuracy: float  # Average accuracy before corrections
    total_corrections: int
    total_errors: int
    correction_accuracy: float  # Average accuracy of corrections
    correction_rate: float  # Average percent of errors with correction attempts
    total_execution_time: float
    files_with_errors: List[str]
    stage_metrics: Dict[
        str, Dict[str, float]
    ]  # Method -> {corrections, correction_accuracy, correction_rate}
    field_metrics: Dict[
        str, Dict[str, float]
    ]  # Field -> {base_accuracy, corrections, correction_accuracy, correction_rate}


class BatchEvaluationResult(BaseModel):
    """Results for batch evaluation."""

    file_results: List["EvaluationResult"]
    overall_metrics: BatchEvaluationMetrics
    timestamp: str


class EvaluationResult(BaseModel):
    """Result of pipeline evaluation."""

    metrics: EvaluationMetrics
    input_file: str
    ground_truth_file: str
    config_file: str
    metadata_file: str
    corrections_file: str
    timestamp: str


class PipelineEvaluator:
    """Evaluator for metadata correction pipeline."""

    def __init__(self, config: MetadataCorrectionConfig) -> None:
        """Initialize evaluator.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self.pipeline = MetadataCorrectionPipeline(config)

    async def evaluate_file(
        self, input_file: Union[str, Path], ground_truth_file: Union[str, Path]
    ) -> EvaluationResult:
        """Evaluate pipeline on a single file.

        Args:
            input_file: Path to input file
            ground_truth_file: Path to ground truth file

        Returns:
            Evaluation result
        """
        logger.info(f"ground_truth_file: {ground_truth_file}")
        logger.info(f"input_file: {input_file}")

        input_file = Path(input_file)
        ground_truth_file = Path(ground_truth_file)

        # Load data
        original_input_df = pd.read_csv(input_file)  # Store original input
        ground_truth_df = pd.read_csv(ground_truth_file)

        # Initialize results
        predictions_df = pd.DataFrame().reindex_like(original_input_df)
        confidence_df = pd.DataFrame().reindex_like(original_input_df)
        error_df = pd.DataFrame().reindex_like(original_input_df)

        # Process file
        start_time = time.time()

        # Process entire DataFrame (use a copy to avoid modifying original)
        input_df = original_input_df.copy()
        state = await self.pipeline.process_metadata(input_df)

        # Update predictions from DataFrame
        predictions_df = state.metadata.copy()

        # Update confidences and errors
        for attempt in state.correction_history:
            confidence_df.at[attempt.row_idx, attempt.column] = attempt.confidence
        for error in state.errors:
            logger.error(error.message)
            error_df.at[error.row_idx, error.column] = True

        execution_time = time.time() - start_time

        # Calculate metrics
        metrics = calculate_overall_metrics(
            ground_truth_df,
            predictions_df,
            original_input_df,  # Use original unprocessed input
            confidence_df,
            error_df,
            state.correction_history,
            execution_time,
        )

        # Save corrected metadata
        metadata_file = (
            self.config.pipeline.output_dir / f"{input_file.stem}_corrected.csv"
        )
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        predictions_df.to_csv(metadata_file, index=False)
        logger.info(f"Saved corrected metadata to {metadata_file}")

        # Save correction attempts
        corrections_file = (
            self.config.pipeline.output_dir / f"{input_file.stem}_corrections.json"
        )
        corrections_data = {
            "correction_history": [
                {
                    "id": str(attempt.id),
                    "method": attempt.method,
                    "row_idx": attempt.row_idx,
                    "column": attempt.column,
                    "proposed_value": attempt.proposed_value,
                    "confidence": attempt.confidence,
                    "timestamp": attempt.timestamp.isoformat(),
                    "metadata": attempt.metadata,
                }
                for attempt in state.correction_history
            ],
            "errors": [
                {
                    "id": str(error.id),
                    "row_idx": error.row_idx,
                    "column": error.column,
                    "value": error.value,
                    "error_type": error.error_type,
                    "message": error.message,
                    "context": error.context,
                }
                for error in state.errors
            ],
        }
        with open(corrections_file, "w") as f:
            json.dump(corrections_data, f, indent=2)
        logger.info(f"Saved correction attempts to {corrections_file}")

        return EvaluationResult(
            metrics=metrics,
            input_file=str(input_file),
            ground_truth_file=str(ground_truth_file),
            config_file=str(self.config.pipeline.schema_path),
            metadata_file=str(metadata_file),
            corrections_file=str(corrections_file),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    async def evaluate_directory(
        self,
        input_dir: Union[str, Path],
        ground_truth_dir: Union[str, Path],
        pattern: str = "*.csv",
        max_concurrency: int = 10,
    ) -> List[EvaluationResult]:
        """Evaluate pipeline on all files in a directory concurrently.

        Args:
            input_dir: Directory containing input files
            ground_truth_dir: Directory containing ground truth files
            pattern: Glob pattern for finding files
            max_concurrency: Maximum number of concurrent evaluations

        Returns:
            List of evaluation results
        """
        input_dir = Path(input_dir)
        ground_truth_dir = Path(ground_truth_dir)
        semaphore = asyncio.Semaphore(max_concurrency)

        # Get total file count for progress tracking
        input_files = list(input_dir.glob(pattern))
        total_files = len(input_files)
        completed_files = 0
        logger.info(
            f"Starting batch evaluation of {total_files} files with max concurrency {max_concurrency}"
        )

        async def bounded_evaluate(input_file: Path) -> Optional[EvaluationResult]:
            nonlocal completed_files
            async with semaphore:  # Limit concurrent executions
                ground_truth_file = ground_truth_dir / input_file.name.replace(
                    "_with_errors", ""
                )
                if not ground_truth_file.exists():
                    logger.warning(f"No ground truth file found for {input_file}")
                    return None
                try:
                    result = await self.evaluate_file(input_file, ground_truth_file)
                    completed_files += 1
                    logger.info(
                        f"Progress: {completed_files}/{total_files} files processed ({(completed_files/total_files)*100:.1f}%)"
                    )
                    return result
                except Exception as e:
                    logger.exception(f"Error evaluating {input_file}")
                    completed_files += 1
                    logger.info(
                        f"Progress: {completed_files}/{total_files} files processed ({(completed_files/total_files)*100:.1f}%)"
                    )
                    return None

        # Create tasks for all files
        tasks = [bounded_evaluate(f) for f in input_files]
        results = [r for r in await asyncio.gather(*tasks) if r is not None]
        logger.info(
            f"Batch evaluation complete. Successfully processed {len(results)}/{total_files} files"
        )
        return results

    def calculate_batch_metrics(
        self, results: List[EvaluationResult]
    ) -> BatchEvaluationMetrics:
        """Calculate overall metrics across all files.

        Args:
            results: List of individual file results

        Returns:
            Aggregated metrics across all files
        """
        logger.info(f"Number of results to process: {len(results)}")

        total_files = len(results)
        logger.info(f"Total files: {total_files}")

        if total_files == 0:
            logger.warning("No results to process - this will cause division by zero")
            return BatchEvaluationMetrics(
                total_files=0,
                base_accuracy=0.0,
                total_corrections=0,
                total_errors=0,
                correction_accuracy=0.0,
                correction_rate=0.0,
                total_execution_time=0.0,
                files_with_errors=[],
                stage_metrics={},
                field_metrics={},
            )

        total_corrections = sum(r.metrics.total_corrections for r in results)
        total_errors = sum(r.metrics.total_errors for r in results)
        total_time = sum(r.metrics.execution_time for r in results)

        logger.info(f"Total corrections across all files: {total_corrections}")
        logger.info(f"Total errors across all files: {total_errors}")
        logger.info(f"Total execution time: {total_time:.2f}s")

        # Log individual file metrics
        for i, r in enumerate(results):
            logger.info(f"File {i+1}: {r.input_file}")
            logger.info(f"  - Corrections: {r.metrics.total_corrections}")
            logger.info(f"  - Accuracy: {r.metrics.correction_accuracy:.2%}")

        # Calculate weighted averages based on number of corrections
        weights = np.array([r.metrics.total_corrections for r in results])
        logger.info(f"Correction weights before normalization: {weights}")
        weights = (
            weights / weights.sum()
            if weights.sum() > 0
            else np.ones_like(weights) / len(weights)
        )
        logger.info(f"Correction weights after normalization: {weights}")

        correction_accuracy = float(
            np.average(
                [r.metrics.correction_accuracy for r in results], weights=weights
            )
        )

        files_with_errors = [
            r.input_file for r in results if r.metrics.total_errors > 0
        ]

        # Calculate base accuracy across all files
        total_cells = 0
        correct_cells = 0
        for r in results:
            # Get number of rows from input file
            input_df = pd.read_csv(r.input_file)
            num_rows = len(input_df)

            # Calculate cells and correct cells
            if r.metrics.field_metrics:
                total_cells += len(r.metrics.field_metrics) * num_rows
                for field, metrics in r.metrics.field_metrics.items():
                    correct_cells += round(metrics.base_accuracy * num_rows)
        base_accuracy = correct_cells / total_cells if total_cells > 0 else 0.0

        # Calculate correction rate
        correction_rate = total_corrections / total_errors if total_errors > 0 else 0.0

        # Aggregate stage metrics
        stage_metrics = {}
        for method in CorrectionMethod:
            stage_corrections = sum(
                r.metrics.stage_metrics[method].corrections for r in results
            )
            if stage_corrections > 0:
                stage_accuracy = float(
                    np.average(
                        [
                            r.metrics.stage_metrics[method].correction_accuracy
                            for r in results
                        ],
                        weights=weights,
                    )
                )
                stage_rate = float(
                    np.average(
                        [
                            r.metrics.stage_metrics[method].correction_rate
                            for r in results
                        ],
                        weights=weights,
                    )
                )
            else:
                stage_accuracy = 0.0
                stage_rate = 0.0

            stage_metrics[str(method)] = {
                "corrections": stage_corrections,
                "correction_accuracy": stage_accuracy,
                "correction_rate": stage_rate,
            }

        # Aggregate field metrics
        field_metrics = {}
        all_fields = set().union(
            *(set(r.metrics.field_metrics.keys()) for r in results)
        )

        for field in all_fields:
            # Get results that have this field
            field_results = [r for r in results if field in r.metrics.field_metrics]
            field_corrections = sum(
                r.metrics.field_metrics[field].corrections for r in field_results
            )

            if field_corrections > 0:
                # Calculate field-specific weights
                field_weights = np.array(
                    [r.metrics.total_corrections for r in field_results]
                )
                field_weights = (
                    field_weights / field_weights.sum()
                    if field_weights.sum() > 0
                    else np.ones_like(field_weights) / len(field_weights)
                )

                logger.debug(
                    f"Field {field} weights: {field_weights}, sum: {field_weights.sum()}"
                )

                # Calculate metrics using field-specific weights
                field_base_accuracy = float(
                    np.average(
                        [
                            r.metrics.field_metrics[field].base_accuracy
                            for r in field_results
                        ]
                    )
                )

                field_accuracy = float(
                    np.average(
                        [
                            r.metrics.field_metrics[field].correction_accuracy
                            for r in field_results
                        ],
                        weights=field_weights,
                    )
                )

                field_rate = float(
                    np.average(
                        [
                            r.metrics.field_metrics[field].correction_rate
                            for r in field_results
                        ],
                        weights=field_weights,
                    )
                )

                logger.debug(
                    f"Field {field} metrics - base_accuracy: {field_base_accuracy:.3f}, correction_accuracy: {field_accuracy:.3f}, correction_rate: {field_rate:.3f}"
                )
            else:
                field_base_accuracy = 1.0
                field_accuracy = 1.0
                field_rate = 0.0
                logger.debug(f"Field {field} has no corrections, using default values")

            field_metrics[field] = {
                "base_accuracy": field_base_accuracy,
                "corrections": field_corrections,
                "correction_accuracy": field_accuracy,
                "correction_rate": field_rate,
            }

        return BatchEvaluationMetrics(
            total_files=total_files,
            base_accuracy=base_accuracy,
            total_corrections=total_corrections,
            total_errors=total_errors,
            correction_accuracy=correction_accuracy,
            correction_rate=correction_rate,
            total_execution_time=total_time,
            files_with_errors=files_with_errors,
            stage_metrics=stage_metrics,
            field_metrics=field_metrics,
        )

    def save_results(
        self,
        results: Union[EvaluationResult, List[EvaluationResult]],
        output_file: Union[str, Path],
    ) -> None:
        """Save evaluation results to file.

        Args:
            results: Evaluation results to save
            output_file: Path to output file
        """
        if not isinstance(results, list):
            results = [results]

        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Calculate batch metrics
        batch_result = BatchEvaluationResult(
            file_results=results,
            overall_metrics=self.calculate_batch_metrics(results),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Convert to JSON-serializable format
        def convert_numpy(obj):
            if isinstance(obj, dict):
                return {k: convert_numpy(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy(v) for v in list(obj)]
            elif hasattr(obj, "item"):  # Convert numpy types
                return obj.item()
            return obj

        data = convert_numpy(batch_result.model_dump())

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved evaluation results to {output_file}")
