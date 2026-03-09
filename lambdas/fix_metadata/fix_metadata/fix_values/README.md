# Fix Values Package

This package provides a metadata correction pipeline that uses various ML/NLP techniques to detect and fix errors in metadata values.

## Features

- Schema-based validation of metadata fields
- Multiple correction strategies:
  - Fuzzy string matching for typos and minor variations
  - Semantic similarity for conceptually related values
  - Statistical inference for pattern-based corrections
  - LLM-powered corrections for complex cases
- Extensible pipeline architecture
- Comprehensive test suite
- Full type hints and static type checking

## Installation

```bash
pip install genai-curator-fix-values
```

For development:

```bash
pip install genai-curator-fix-values[dev]
```

## Usage

Basic usage:

```python
from genai_curator.fix_values.pipeline import (
    MetadataCorrectionConfig,
    MetadataCorrectionPipeline,
    PipelineSettings
)

# Configure pipeline
config = MetadataCorrectionConfig(
    pipeline=PipelineSettings(
        schema_path="path/to/schema.json",
        output_dir="path/to/output"
    )
)

# Create pipeline
pipeline = MetadataCorrectionPipeline(config)

# Process metadata
metadata = {
    "field1": "valu1",  # Should be "value1"
    "field2": 50
}

# Process single record
async for state in pipeline.process_metadata(metadata):
    print(f"Iteration {state.iteration}:")
    print(f"Current metadata: {state.metadata}")
    print(f"Errors: {len(state.errors)}")
    print(f"Corrections: {len(state.correction_history)}")

# Process batch of files
async for states in pipeline.process_batch("input/dir", "output/dir"):
    for filename, state in states.items():
        print(f"Processed {filename}")
        print(f"Final errors: {len(state.errors)}")
```

## Schema Format

The schema is defined in JSON/YAML format:

```yaml
version: "1.0.0"
description: "Example metadata schema"
fields:
  - name: field1
    type: string
    required: true
    valid_values:
      - value1
      - value2
      - value3
    description: "Example field with controlled vocabulary"

  - name: field2
    type: integer
    required: false
    constraints:
      min: 0
      max: 100
    description: "Example numeric field"
```

## Development

Setup:

```bash
# Clone repo
git clone https://github.com/genai-curator/genai-curator.git
cd genai-curator/src/genai_curator/fix_values

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run type checking
mypy .
```

## License

Apache License 2.0
