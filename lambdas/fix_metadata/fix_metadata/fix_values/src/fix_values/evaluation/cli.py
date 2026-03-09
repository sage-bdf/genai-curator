# This deliverable is considered developed content as defined in contract between BDF parties.


"""Command-line interface for evaluation package."""

import asyncio
import json
import traceback
from pathlib import Path
from typing import Optional, cast

import click
from loguru import logger
from pydantic import BaseModel, validator

from fix_values.evaluation import PipelineEvaluator
from fix_values.pipeline import MetadataCorrectionConfig, PipelineSettings
from fix_values.utils.logging import setup_logging


class EvaluationConfig(BaseModel):
    """Configuration for evaluation."""

    schema_path: Path
    input_path: Path
    ground_truth_path: Path
    output_path: Path
    pattern: str = "*.csv"
    log_level: str = "INFO"
    log_file: Optional[Path] = None

    @validator(
        "schema_path", "input_path", "ground_truth_path", "output_path", pre=True
    )
    def ensure_path(cls, v: Optional[Path]) -> Path:
        """Ensure value is a Path object."""
        if v is None:
            raise ValueError("Path cannot be None")
        if not isinstance(v, Path):
            return Path(str(v))
        return v


@click.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to evaluation config file",
)
@click.option(
    "--schema",
    "-s",
    type=click.Path(exists=True, path_type=Path),
    help="Path to schema file",
)
@click.option(
    "--input",
    "-i",
    type=click.Path(exists=True, path_type=Path),
    help="Path to input file or directory",
)
@click.option(
    "--ground-truth",
    "-g",
    type=click.Path(exists=True, path_type=Path),
    help="Path to ground truth file or directory",
)
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), help="Path to output file"
)
@click.option(
    "--pattern",
    "-p",
    type=str,
    default="*.csv",
    help="File pattern to match (when input is directory)",
)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Logging level",
)
@click.option(
    "--log-file", "-f", type=click.Path(path_type=Path), help="Path to log file"
)
def main(
    config: Optional[Path] = None,
    schema: Optional[Path] = None,
    input: Optional[Path] = None,
    ground_truth: Optional[Path] = None,
    output: Optional[Path] = None,
    pattern: str = "*.csv",
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
) -> None:
    """Evaluate metadata correction pipeline.

    Args:
        config: Path to evaluation config file
        schema: Path to schema file
        input: Path to input file or directory
        ground_truth: Path to ground truth file or directory
        output: Path to output file
        pattern: File pattern to match (when input is directory)
        log_level: Logging level
    """
    # Load config
    if config:
        with open(config) as f:
            config_data = json.load(f)
            eval_config = EvaluationConfig(**config_data)
    else:
        if not all([schema, input, ground_truth, output]):
            raise click.UsageError(
                "Must provide either config file or all of: "
                "schema, input, ground_truth, output"
            )

        eval_config = EvaluationConfig(
            schema_path=cast(Path, schema),
            input_path=cast(Path, input),
            ground_truth_path=cast(Path, ground_truth),
            output_path=cast(Path, output),
            pattern=pattern,
            log_level=log_level,
            log_file=log_file,
        )

    # Setup logging
    setup_logging(level=eval_config.log_level, log_file=eval_config.log_file)

    # Create pipeline config
    pipeline_config = MetadataCorrectionConfig(
        pipeline=PipelineSettings(
            schema_path=eval_config.schema_path,
            output_dir=eval_config.output_path.parent,
        )
    )

    # Create evaluator
    evaluator = PipelineEvaluator(pipeline_config)

    # Run evaluation
    try:
        if eval_config.input_path.is_file():
            # Single file evaluation
            result = asyncio.run(
                evaluator.evaluate_file(
                    eval_config.input_path, eval_config.ground_truth_path
                )
            )
            results = [result]
        else:
            # Directory evaluation
            results = asyncio.run(
                evaluator.evaluate_directory(
                    eval_config.input_path,
                    eval_config.ground_truth_path,
                    eval_config.pattern,
                )
            )

        # Save results
        output_dir = eval_config.output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Use consistent naming: input.csv -> input_evaluation.json
        eval_output = output_dir / f"{eval_config.output_path.stem}_evaluation.json"
        evaluator.save_results(results, eval_output)

    except Exception as e:
        logger.exception("Error during evaluation")
        logger.exception(traceback.format_exc())
        raise click.ClickException(str(e))


if __name__ == "__main__":
    main()
