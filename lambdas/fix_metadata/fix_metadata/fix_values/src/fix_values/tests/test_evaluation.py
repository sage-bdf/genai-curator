# This deliverable is considered developed content as defined in contract between BDF parties.


"""Tests for evaluation package."""

import json
from pathlib import Path
from typing import Dict

import pandas as pd
import pytest

from fix_values.evaluation import (
    EvaluationMetrics,
    EvaluationResult,
    FieldMetrics,
    PipelineEvaluator,
    calculate_field_metrics,
    calculate_overall_metrics,
)
from fix_values.pipeline import MetadataCorrectionConfig, PipelineSettings


@pytest.fixture
def test_data() -> Dict[str, pd.DataFrame]:
    """Create test data for evaluation."""
    # Ground truth data
    ground_truth = pd.DataFrame(
        {
            "field1": ["value1", "value2", "value3"],
            "field2": ["value4", "value5", "value6"],
        }
    )

    # Predictions with some errors
    predictions = pd.DataFrame(
        {
            "field1": ["value1", "wrong", "value3"],
            "field2": ["value4", "value5", "wrong"],
        }
    )

    # Confidence scores
    confidences = pd.DataFrame({"field1": [1.0, 0.8, 1.0], "field2": [1.0, 1.0, 0.7]})

    # Error indicators
    errors = pd.DataFrame(
        {"field1": [False, True, False], "field2": [False, False, True]}
    )

    return {
        "ground_truth": ground_truth,
        "predictions": predictions,
        "confidences": confidences,
        "errors": errors,
    }


def test_calculate_field_metrics(test_data: Dict[str, pd.DataFrame]) -> None:
    """Test calculation of field-level metrics."""
    metrics = calculate_field_metrics(
        test_data["ground_truth"]["field1"],
        test_data["predictions"]["field1"],
        test_data["confidences"]["field1"],
        test_data["errors"]["field1"],
    )

    assert isinstance(metrics, FieldMetrics)
    assert metrics.accuracy == pytest.approx(0.667, abs=0.001)
    assert metrics.precision == pytest.approx(0.667, abs=0.001)
    assert metrics.recall == pytest.approx(0.667, abs=0.001)
    assert metrics.f1_score == pytest.approx(0.667, abs=0.001)
    assert metrics.num_corrections == 1
    assert metrics.num_errors == 1
    assert metrics.correction_rate == 1.0
    assert metrics.avg_confidence == 0.8


def test_calculate_overall_metrics(test_data: Dict[str, pd.DataFrame]) -> None:
    """Test calculation of overall metrics."""
    metrics = calculate_overall_metrics(
        test_data["ground_truth"],
        test_data["predictions"],
        test_data["confidences"],
        test_data["errors"],
        execution_time=1.0,
    )

    assert isinstance(metrics, EvaluationMetrics)
    assert metrics.overall_accuracy == pytest.approx(0.667, abs=0.001)
    assert metrics.overall_precision == pytest.approx(0.667, abs=0.001)
    assert metrics.overall_recall == pytest.approx(0.667, abs=0.001)
    assert metrics.overall_f1 == pytest.approx(0.667, abs=0.001)
    assert metrics.total_corrections == 2
    assert metrics.total_errors == 2
    assert metrics.avg_confidence == pytest.approx(0.75, abs=0.001)
    assert metrics.execution_time == 1.0

    assert len(metrics.field_metrics) == 2
    assert all(isinstance(m, FieldMetrics) for m in metrics.field_metrics.values())


@pytest.fixture
def temp_files(tmp_path: Path, test_data: Dict[str, pd.DataFrame]) -> Dict[str, Path]:
    """Create temporary files for testing."""
    # Save test data to files
    input_file = tmp_path / "input.csv"
    test_data["predictions"].to_csv(input_file, index=False)

    ground_truth_file = tmp_path / "ground_truth.csv"
    test_data["ground_truth"].to_csv(ground_truth_file, index=False)

    schema_file = tmp_path / "schema.json"
    schema = {"fields": {"field1": {"type": "string"}, "field2": {"type": "string"}}}
    with open(schema_file, "w") as f:
        json.dump(schema, f)

    output_file = tmp_path / "results.json"

    return {
        "input": input_file,
        "ground_truth": ground_truth_file,
        "schema": schema_file,
        "output": output_file,
    }


@pytest.mark.asyncio
async def test_evaluator(temp_files: Dict[str, Path]) -> None:
    """Test PipelineEvaluator."""
    # Create config
    config = MetadataCorrectionConfig(
        pipeline=PipelineSettings(
            schema_path=temp_files["schema"], output_dir=temp_files["output"].parent
        )
    )

    # Create evaluator
    evaluator = PipelineEvaluator(config)

    # Test single file evaluation
    result = await evaluator.evaluate_file(
        temp_files["input"], temp_files["ground_truth"]
    )

    assert isinstance(result, EvaluationResult)
    assert result.metrics.overall_accuracy == pytest.approx(0.667, abs=0.001)
    assert result.input_file == str(temp_files["input"])
    assert result.ground_truth_file == str(temp_files["ground_truth"])

    # Test directory evaluation
    results = await evaluator.evaluate_directory(
        temp_files["input"].parent, temp_files["ground_truth"].parent
    )

    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0], EvaluationResult)

    # Test saving results
    evaluator.save_results(results, temp_files["output"])
    assert temp_files["output"].exists()

    with open(temp_files["output"]) as f:
        saved_data = json.load(f)

    assert isinstance(saved_data, list)
    assert len(saved_data) == 1
    assert "metrics" in saved_data[0]
    assert "input_file" in saved_data[0]
    assert "ground_truth_file" in saved_data[0]
