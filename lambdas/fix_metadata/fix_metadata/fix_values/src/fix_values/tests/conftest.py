# This deliverable is considered developed content as defined in contract between BDF parties.


"""Test configuration and fixtures."""

from pathlib import Path
from typing import Dict, List

import pytest
from _pytest.fixtures import FixtureRequest

from fix_values.pipeline.core.models import Schema, SchemaField
from fix_values.pipeline.core.settings import (
    AWSSettings,
    FuzzyMatchSettings,
    LLMSettings,
    MetadataCorrectionConfig,
    PipelineSettings,
    SemanticSettings,
    ValidationSettings,
)


@pytest.fixture
def data_dir(request: FixtureRequest) -> Path:
    """Get test data directory."""
    return Path(request.module.__file__).parent / "data"


@pytest.fixture
def test_schema() -> Schema:
    """Create test schema."""
    return Schema(
        fields=[
            SchemaField(
                name="field1",
                type="string",
                required=True,
                valid_values=["value1", "value2", "value3"],
            ),
            SchemaField(
                name="field2",
                type="integer",
                required=False,
                constraints={"min": 0, "max": 100},
            ),
        ]
    )


@pytest.fixture
def test_config(test_schema: Schema, tmp_path: Path) -> MetadataCorrectionConfig:
    """Create test configuration."""
    schema_path = tmp_path / "schema.json"
    with open(schema_path, "w") as f:
        json.dump(test_schema.dict(), f)

    return MetadataCorrectionConfig(
        pipeline=PipelineSettings(
            schema_path=schema_path, output_dir=tmp_path / "output"
        ),
        validation=ValidationSettings(),
        fuzzy=FuzzyMatchSettings(),
        semantic=SemanticSettings(),
        llm=LLMSettings(),
        aws=AWSSettings(),
    )


@pytest.fixture
def test_metadata() -> Dict[str, str]:
    """Create test metadata."""
    return {"field1": "value1", "field2": 50}


@pytest.fixture
def test_errors() -> List[Dict[str, str]]:
    """Create test errors."""
    return [
        {
            "field": "field1",
            "value": "invalid",
            "error_type": "vocabulary",
            "message": "Invalid value",
        },
        {
            "field": "field2",
            "value": 200,
            "error_type": "format",
            "message": "Value out of range",
        },
    ]
