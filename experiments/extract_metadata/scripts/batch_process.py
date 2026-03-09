#!/usr/bin/env python3
# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Batch Processing Script for Extract Metadata

This script processes multiple files in parallel using the ExtractMetadataClient's
process_files method. It extracts metadata from documents based on a specified schema.
"""

import argparse
import glob
import os
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add client directory to path to import client modules
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../client/src"))
)

from extract_client import ExtractMetadataClient
from utils import (
    batch_status_callback,
    load_entity_filenames_from_directory,
    map_files_to_entities,
)


def batch_process_files(
    input_dir: str,
    ground_truth_dir: Optional[str] = None,
    schema_name: str = "nf",
    schema_key: str = "extract_metadata/nf/schema.json",
    max_workers: int = 5,
    poll_interval: int = 15,
    max_time: int = 1800,
    output_dir: str = "output",
    skip_extensions: List[str] = None,
) -> Dict[str, Any]:
    """
    Process multiple files in parallel using the ExtractMetadataClient.

    Args:
        input_dir: Directory containing input files to process
        ground_truth_dir: Directory containing ground truth CSV files (optional)
        schema_name: Name of the schema to use
        schema_key: Key for the schema file in S3
        max_workers: Maximum number of parallel workers
        poll_interval: Interval in seconds to check job status
        max_time: Maximum time in seconds to wait for all jobs
        output_dir: Directory to save output files
        skip_extensions: List of file extensions to skip

    Returns:
        Dictionary containing processing results
    """
    # Create client
    client = ExtractMetadataClient()
    print(f"API URL: {client.api_url}")
    print(f"API Key configured: {'Yes' if client.api_key else 'No'}")

    # Get all files in the input directory
    files = sorted(glob.glob(os.path.join(input_dir, "*")))
    print(f"Found {len(files)} files in {input_dir}")

    # Display file types
    file_types = {}
    for file in files:
        ext = os.path.splitext(file)[1]
        if ext in file_types:
            file_types[ext] += 1
        else:
            file_types[ext] = 1

    print("\nFile types:")
    for ext, count in file_types.items():
        print(f"{ext}: {count} files")

    # Set default skip extensions if not provided
    if skip_extensions is None:
        skip_extensions = [".tgz"]

    # Map files to entity filenames if ground truth directory is provided
    file_to_entities = {}
    if ground_truth_dir:
        # Load entity filenames from all CSV files in the ground truth directory
        entity_filenames_by_file, all_names = load_entity_filenames_from_directory(
            ground_truth_dir
        )

        # Map files to their corresponding entity filenames
        file_to_entities = map_files_to_entities(files, entity_filenames_by_file)
        print(f"Mapped {len(file_to_entities)} files to entity filenames")

    print(f"Starting processing for {len(files)} files...")

    # Process all files using the client's built-in process_files method
    result = client.process_files(
        files=files,
        schema_name=schema_name,
        schema_key=schema_key,
        file_to_entities=file_to_entities,
        skip_extensions=skip_extensions,
        max_workers=max_workers,
        poll_interval=poll_interval,
        max_time=max_time,
        download_results_flag=True,
        output_dir=output_dir,
        callback=batch_status_callback,
    )

    print(f"\n\nProcessed {result['processed_files']} of {result['total_files']} files")
    return result


def main():
    """Main function to parse arguments and run batch processing."""
    parser = argparse.ArgumentParser(
        description="Batch process files for metadata extraction"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing input files",
    )
    parser.add_argument(
        "--ground-truth-dir",
        help="Directory containing ground truth CSV files",
    )
    parser.add_argument(
        "--schema-name",
        default="nf",
        help="Name of the schema to use",
    )
    parser.add_argument(
        "--schema-key",
        default="extract_metadata/nf/schema.json",
        help="Key for the schema file in S3",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Maximum number of parallel workers",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=15,
        help="Interval in seconds to check job status",
    )
    parser.add_argument(
        "--max-time",
        type=int,
        default=1800,
        help="Maximum time in seconds to wait for all jobs",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to save output files",
    )
    parser.add_argument(
        "--skip-extensions",
        nargs="+",
        default=[".tgz"],
        help="List of file extensions to skip",
    )

    args = parser.parse_args()

    batch_process_files(
        input_dir=args.input_dir,
        ground_truth_dir=args.ground_truth_dir,
        schema_name=args.schema_name,
        schema_key=args.schema_key,
        max_workers=args.max_workers,
        poll_interval=args.poll_interval,
        max_time=args.max_time,
        output_dir=args.output_dir,
        skip_extensions=args.skip_extensions,
    )


if __name__ == "__main__":
    main()
