# This deliverable is considered developed content as defined in contract between BDF parties.


"""Tests for metadata correction pipeline."""

import json
from pathlib import Path

import pytest
from fix_values.pipeline import (
    FuzzyMatchNode,
    MetadataCorrectionPipeline,
    NodeConfig,
    ValidationNode,
)
from fix_values.pipeline.core.models import (
    CorrectionMethod,
    Error,
    ErrorType,
    PipelineState,
    Schema,
    SchemaField,
)
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
def test_pipeline(test_config: MetadataCorrectionConfig) -> MetadataCorrectionPipeline:
    """Create test pipeline."""
    return MetadataCorrectionPipeline(test_config)


@pytest.mark.asyncio
async def test_validation_node(test_schema: Schema) -> None:
    """Test validation node."""
    node = ValidationNode(schema=test_schema, config=NodeConfig(name="test_validation"))

    # Test valid metadata
    state = PipelineState(metadata={"field1": "value1", "field2": 50})
    new_state, result = await node.process(state)
    assert result.is_valid
    assert not result.errors

    # Test invalid metadata
    state = PipelineState(metadata={"field1": "invalid", "field2": 200})
    new_state, result = await node.process(state)
    assert not result.is_valid
    assert len(result.errors) == 2
    assert result.errors[0].error_type == ErrorType.VOCABULARY
    assert result.errors[1].error_type == ErrorType.FORMAT


@pytest.mark.asyncio
async def test_fuzzy_match_node(test_schema: Schema) -> None:
    """Test fuzzy matching node."""
    node = FuzzyMatchNode(
        schema=test_schema, config=NodeConfig(name="test_fuzzy"), threshold=0.8
    )

    # Test fuzzy matching
    error = Error(
        field="field1",
        value="valu1",
        error_type=ErrorType.VOCABULARY,
        message="Invalid value",
    )

    state = PipelineState(metadata={"field1": "valu1"}, errors=[error])

    new_state, results = await node.process(state)
    assert results
    assert results[0].success
    assert results[0].attempt.proposed_value == "value1"
    assert results[0].attempt.confidence >= 0.8


@pytest.mark.asyncio
async def test_pipeline_processing(test_pipeline: MetadataCorrectionPipeline) -> None:
    """Test end-to-end pipeline processing."""
    metadata = {
        "field1": "valu1",  # Should be corrected to "value1"
        "field2": 50,  # Valid value
    }

    states = []
    async for state in test_pipeline.process_metadata(metadata):
        states.append(state)

    assert states
    final_state = states[-1]

    # Check corrections
    assert final_state.metadata["field1"] == "value1"
    assert final_state.metadata["field2"] == 50

    # Check correction history
    assert final_state.correction_history
    assert any(
        attempt.method == CorrectionMethod.FUZZY
        for attempt in final_state.correction_history
    )
