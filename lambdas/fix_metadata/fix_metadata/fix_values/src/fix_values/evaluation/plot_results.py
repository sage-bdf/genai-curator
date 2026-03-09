# This deliverable is considered developed content as defined in contract between BDF parties.


"""Script to generate visualizations from evaluation results."""

import asyncio
import json
import logging
from pathlib import Path

from fix_values.evaluation.visualizations import (
    plot_evaluation_metrics,
    plot_field_metrics,
    plot_stage_metrics,
    save_visualizations,
)

logger = logging.getLogger(__name__)


async def plot_evaluation_results(results_file: str, output_dir: str) -> None:
    """Generate and save visualizations from evaluation results.

    Args:
        results_file: Path to JSON results file
        output_dir: Directory to save visualizations in
    """
    # Load results
    with open(results_file) as f:
        results = json.load(f)

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        # Generate visualizations for each file result
        for i, file_result in enumerate(results["file_results"]):
            prefix = f"file_{i}"
            logger.info(
                f"Generating visualizations for file {i+1}/{len(results['file_results'])}"
            )

            try:
                # Plot stage metrics
                stage_figs = plot_stage_metrics(file_result["metrics"]["stage_metrics"])
                save_visualizations(stage_figs, output_dir, f"{prefix}_stage")

                # Plot field metrics
                field_figs = plot_field_metrics(file_result["metrics"]["field_metrics"])
                save_visualizations(field_figs, output_dir, f"{prefix}_field")

                # Plot overall metrics
                eval_figs = plot_evaluation_metrics(file_result["metrics"])
                save_visualizations(eval_figs, output_dir, f"{prefix}_overall")
            except KeyError as e:
                logger.error(f"Missing required key in file result {i}: {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing file result {i}: {e}")
                continue

        # Generate visualizations for overall batch metrics
        logger.info("Generating overall batch visualizations")

        overall_stage_figs = plot_stage_metrics(
            results["overall_metrics"]["stage_metrics"]
        )
        save_visualizations(overall_stage_figs, output_dir, "overall_stage")

        overall_field_figs = plot_field_metrics(
            results["overall_metrics"]["field_metrics"]
        )
        save_visualizations(overall_field_figs, output_dir, "overall_field")

        overall_eval_figs = plot_evaluation_metrics(results["overall_metrics"])
        save_visualizations(overall_eval_figs, output_dir, "overall")

        logger.info(f"All visualizations saved to {output_dir}")
    except KeyError as e:
        logger.error(f"Missing required key in results: {e}")
    except Exception as e:
        logger.error(f"Error generating visualizations: {e}")


def main():
    """Command line interface."""
    import argparse

    # Set up logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Generate visualizations from evaluation results"
    )
    parser.add_argument("results_file", help="Path to JSON results file")
    parser.add_argument("output_dir", help="Directory to save visualizations in")

    args = parser.parse_args()

    try:
        asyncio.run(plot_evaluation_results(args.results_file, args.output_dir))
    except FileNotFoundError:
        logger.error(f"Results file not found: {args.results_file}")
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in results file: {args.results_file}")
    except Exception as e:
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    main()
