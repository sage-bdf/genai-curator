# Metadata Correction Pipeline Evaluation

This package provides tools for evaluating the metadata correction pipeline's performance against ground truth data.

## Features

- Evaluate single files or entire directories
- Calculate field-level and overall metrics:
  - Accuracy
  - Precision
  - Recall
  - F1 Score
  - Number of corrections
  - Correction rate
  - Confidence scores
- Support for configuration via file or CLI arguments
- JSON output format for easy analysis

## Usage

### Command Line Interface

The `evaluate_pipeline.py` script provides a CLI for running evaluations:

```bash
# Evaluate a single file
python evaluate_pipeline.py \
  --schema schema.json \
  --input input.csv \
  --ground-truth ground_truth.csv \
  --output results.json

# Evaluate a directory
python evaluate_pipeline.py \
  --schema schema.json \
  --input input_dir \
  --ground-truth ground_truth_dir \
  --output results.json \
  --pattern "*.csv"

python -m genai_curator.fix_values.evaluation   --schema /home/ubuntu/projects/data/pz-nf-testing-data/schema/NF.jsonid   --input /home/ubuntu/projects/data/synthetic_error   --ground-truth /home/ubuntu/projects/data/ground_truth  --output results_batch.json --log-level DEBUG --log-file pipeline_results_batch.log



python -m genai_curator.fix_values.evaluation   --schema /home/ubuntu/projects/data/pz-nf-testing-data/schema/NF.jsonid   --input /home/ubuntu/projects/data/synthetic_error_limited   --ground-truth /home/ubuntu/projects/data/ground_truth  --output results_batch_limited.json --log-level INFO --log-file pipeline_results_batch_limited.log

# Use a config file
python evaluate_pipeline.py --config eval_config.json
```

### Configuration File

Example configuration file (`eval_config.json`):

```json
{
  "schema_path": "path/to/schema.json",
  "input_path": "path/to/input",
  "ground_truth_path": "path/to/ground_truth",
  "output_path": "path/to/results.json",
  "pattern": "*.csv",
  "log_level": "INFO"
}
```

### Python API

```python
from genai_curator.fix_values.evaluation import PipelineEvaluator
from genai_curator.fix_values.pipeline import MetadataCorrectionConfig

# Create evaluator
config = MetadataCorrectionConfig(...)
evaluator = PipelineEvaluator(config)

# Evaluate single file
result = await evaluator.evaluate_file("input.csv", "ground_truth.csv")

# Evaluate directory
results = await evaluator.evaluate_directory("input_dir", "ground_truth_dir")

# Save results
evaluator.save_results(results, "results.json")
```

## Output Format

The evaluation results are saved in JSON format:

```json
[
  {
    "metrics": {
      "overall_accuracy": 0.95,
      "overall_precision": 0.92,
      "overall_recall": 0.94,
      "overall_f1": 0.93,
      "total_corrections": 100,
      "total_errors": 120,
      "avg_confidence": 0.85,
      "field_metrics": {
        "field_name": {
          "accuracy": 0.96,
          "precision": 0.93,
          "recall": 0.95,
          "f1_score": 0.94,
          "num_corrections": 50,
          "num_errors": 55,
          "correction_rate": 0.91,
          "avg_confidence": 0.87
        }
      }
    },
    "input_file": "input.csv",
    "ground_truth_file": "ground_truth.csv",
    "config_file": "schema.json",
    "timestamp": "2025-06-03 01:20:00"
  }
]
```

## Metrics

- **Accuracy**: Proportion of correct predictions (including both corrected and already correct values)
- **Precision**: Proportion of correct corrections among all corrections made
- **Recall**: Proportion of errors that were successfully corrected
- **F1 Score**: Harmonic mean of precision and recall
- **Correction Rate**: Proportion of errors that were attempted to be corrected
- **Confidence Score**: Model's confidence in its corrections

## Development

### Adding New Metrics

To add new evaluation metrics:

1. Add the metric to the `FieldMetrics` or `EvaluationMetrics` class in `metrics.py`
2. Implement calculation in `calculate_field_metrics` or `calculate_overall_metrics`
3. Update tests in `tests/test_evaluation.py`

### Running Tests

```bash
pytest genai_curator/fix_values/tests/test_evaluation.py
```
