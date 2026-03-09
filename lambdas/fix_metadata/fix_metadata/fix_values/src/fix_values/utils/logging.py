# This deliverable is considered developed content as defined in contract between BDF parties.


"""Logging utilities for metadata correction pipeline."""

from pathlib import Path
from typing import Optional, Union

from loguru import logger


def setup_logging(
    level: Union[str, int] = "INFO",
    log_file: Optional[Union[str, Path]] = None,
    format_string: Optional[str] = None,
) -> None:
    """Configure logging for the package.

    Args:
        level: Logging level (default: INFO)
        log_file: Optional path to log file
        format_string: Optional custom format string
    """
    # Remove default handler
    logger.remove()

    # Configure format
    if format_string is None:
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
            "[<level>{level}</level>] "
            "<cyan>{name}</cyan>: "
            "{message} "
            "(<cyan>{file}:{line}</cyan>)"
        )

    # Add console handler
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level=level,
        format=format_string,
        colorize=True,
    )

    # Add file handler if specified
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            sink=str(log_file), level=level, format=format_string, rotation="10 MB"
        )
