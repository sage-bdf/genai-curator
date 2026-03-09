# This deliverable is considered developed content as defined in contract between BDF parties.


"""Tests for synthetic data generation."""

from pathlib import Path

import pandas as pd
import pytest
from fix_values.pipeline import (
    MetadataCorrectionConfig,
    MetadataCorrectionPipeline,
    Schema,
)
from fix_values.synthetic.error_types import (
    FormatError,
    MissingValueError,
    VocabularyError,
)
from fix_values.synthetic.generator import ErrorGenerator, ErrorGeneratorConfig


@pytest.fixture
def test_data() -> pd.DataFrame:
    """Create test data."""
    return pd.DataFrame(
        {"field1": ["value1", "value2", "value3"] * 3, "field2": list(range(50, 59))}
    )


@pytest.fixture
def error_config() -> ErrorGeneratorConfig:
    """Create error generator config."""
    return ErrorGeneratorConfig(
        error_rate=0.2,
        error_types=[
            VocabularyError(weight=0.4),
            FormatError(weight=0.3),
            MissingValueError(weight=0.3),
        ],
    )


def test_error_generation(
    test_data: pd.DataFrame, error_config: ErrorGeneratorConfig, test_schema: Schema
) -> None:
    """Test error generation."""
    generator = ErrorGenerator(error_config)

    # Generate errors
    df_with_errors = generator.add_errors(test_data, test_schema)

    # Check error rate
    total_cells = len(test_data) * len(test_data.columns)
    error_cells = (df_with_errors != test_data).sum().sum()
    error_rate = error_cells / total_cells

    assert abs(error_rate - error_config.error_rate) < 0.1

    # Check error types
    for col in df_with_errors.columns:
        field = test_schema.get_field(col)
        if not field:
            continue

        # Check vocabulary errors
        if field.valid_values:
            invalid_values = ~df_with_errors[col].isin(field.valid_values)
            assert invalid_values.any()

        # Check format errors
        if field.type == "integer":
            non_ints = ~df_with_errors[col].apply(
                lambda x: isinstance(x, int) or pd.isna(x)
            )
            assert non_ints.any()

        # Check missing values
        assert df_with_errors[col].isna().any()


@pytest.mark.asyncio
async def test_error_correction(
    test_data: pd.DataFrame,
    error_config: ErrorGeneratorConfig,
    test_schema: Schema,
    test_config: MetadataCorrectionConfig,
    tmp_path: Path,
) -> None:
    """Test error correction pipeline on synthetic data."""
    # Generate errors
    generator = ErrorGenerator(error_config)
    df_with_errors = generator.add_errors(test_data, test_schema)

    # Save to CSV
    input_file = tmp_path / "test_with_errors.csv"
    df_with_errors.to_csv(input_file, index=False)

    # Run correction pipeline
    pipeline = MetadataCorrectionPipeline(test_config)
    output_dir = tmp_path / "output"

    async for states in pipeline.process_batch(tmp_path, output_dir):
        # Check corrections
        output_file = output_dir / "test_with_errors_corrected.csv"
        assert output_file.exists()

        df_corrected = pd.read_csv(output_file)

        # Check that corrections match original data
        pd.testing.assert_frame_equal(df_corrected, test_data)
