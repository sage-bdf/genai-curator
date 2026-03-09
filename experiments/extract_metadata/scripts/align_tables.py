#!/usr/bin/env python3
# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Align Tables Script

This script provides a command-line interface for aligning and joining tables
from inferred outputs and ground truth data.
"""

import argparse
import os
import sys

# Add the parent directory to the Python path so we can import from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.table_aligner import TableAligner


def main():
    parser = argparse.ArgumentParser(
        description="Align and join tables from inferred outputs and ground truth."
    )
    parser.add_argument(
        "--pred-dir",
        type=str,
        default="../data/predicted",
        help="Directory containing predicted/inferred tables",
    )
    parser.add_argument(
        "--gt-dir",
        type=str,
        default="../data/ground_truth",
        help="Directory containing ground truth tables",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="../data/output",
        help="Directory to save aligned tables",
    )
    parser.add_argument(
        "--file-id",
        type=str,
        help="Process only a specific file ID (e.g., '1' for nf_1)",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List available file IDs without processing",
    )

    args = parser.parse_args()

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)

    # Create the aligner
    aligner = TableAligner(
        args.pred_dir,
        args.gt_dir,
        args.output_dir,
    )

    if args.list_files:
        file_ids = aligner.get_matching_file_ids()
        print(f"Found {len(file_ids)} matching files:")
        for file_id in file_ids:
            print(f"  - {file_id}")
        return

    # Process files
    if args.file_id:
        print(f"Processing file ID: {args.file_id}")
        aligner.process_file(args.file_id)
    else:
        print("Processing all matching files...")
        aligner.process_all_files()

    print(f"\nAligned tables saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
