# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Utility functions for the metadata clients.

This module provides utility functions for the metadata clients.
"""

import glob
import mimetypes
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import boto3
import pandas as pd


def get_file_info(file_path: str) -> Dict[str, str]:
    """Get information about a file.

    Args:
        file_path: The path to the file.

    Returns:
        A dictionary containing information about the file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_name = os.path.basename(file_path)
    file_extension = os.path.splitext(file_path)[1][1:]  # Remove the dot
    mime_type, _ = mimetypes.guess_type(file_path)

    # If mime_type is None, use a default based on extension
    if mime_type is None:
        extension_to_mime = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "doc": "application/msword",
            "txt": "text/plain",
            "rtf": "application/rtf",
            "zip": "application/zip",
            "xml": "application/xml",
            "csv": "text/csv",
            "json": "application/json",
        }
        mime_type = extension_to_mime.get(
            file_extension.lower(), "application/octet-stream"
        )

    return {
        "file_name": file_name,
        "file_extension": file_extension,
        "mime_type": mime_type,
    }


def download_results(output_location: str, local_path: str) -> Optional[str]:
    """
    Download results from S3.

    Args:
        output_location: The S3 URI of the results.
        local_path: The local path to save the results to.

    Returns:
        The local path if the download was successful, None otherwise.
    """
    if not output_location:
        return None

    # Extract bucket and key from S3 URI
    if output_location.startswith("s3://"):
        parts = output_location.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""
    else:
        return None

    try:
        # Create S3 client
        s3_client = boto3.client("s3")

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)

        # Download the file
        s3_client.download_file(bucket, key, local_path)
        return local_path
    except Exception:
        return None


def default_status_callback(
    status_data: Dict[str, Any], attempt: int, max_attempts: int
) -> None:
    """
    Default callback function for status updates.

    Args:
        status_data: The status data.
        attempt: The current attempt number.
        max_attempts: The maximum number of attempts.
    """
    status = status_data.get("status", "UNKNOWN")
    print(f"\nAttempt {attempt}/{max_attempts}: Status = {status}")


def detailed_status_callback(
    status_data: Dict[str, Any], attempt: int, max_attempts: int
) -> None:
    """
    Detailed callback function for status updates with state transitions.

    Args:
        status_data: The status data.
        attempt: The current attempt number.
        max_attempts: The maximum number of attempts.
    """
    print(f"\n📊 Status check {attempt}/{max_attempts}...")

    # Print basic status information
    status = status_data.get("status", "UNKNOWN")
    print(f"Status: {status}")

    # Print detailed execution information if available
    execution_status = status_data.get("executionStatus", {})
    if execution_status:
        print(f"Current state: {execution_status.get('currentState', 'Unknown')}")
        print(f"Execution status: {execution_status.get('status', 'Unknown')}")

        # Print state transitions if available
        state_transitions = execution_status.get("stateTransitions", [])
        if state_transitions:
            print("\nState transitions:")
            for i, transition in enumerate(state_transitions):
                print(
                    f"  {i+1}. {transition.get('state')} at {transition.get('enteredAt')}"
                )


def batch_status_callback(
    active_jobs: List[Dict[str, Any]], completed_jobs: List[Dict[str, Any]]
) -> None:
    """
    Callback function for batch processing status updates.

    Args:
        active_jobs: List of active jobs.
        completed_jobs: List of completed jobs.
    """
    print(f"Active jobs: {len(active_jobs)}, Completed jobs: {len(completed_jobs)}")

    # Print details of active jobs
    if active_jobs:
        print("\nActive jobs:")
        for job in active_jobs[:5]:  # Show first 5 active jobs
            job_info = f"{job['file_name']}: Execution ARN {job.get('execution_arn', 'Unknown')[-8:]}"
            if job.get("has_entities", False):
                job_info += f" (with {job.get('entity_count', 0)} entities)"
            print(f"  {job_info}")

    # Print details of recently completed jobs
    if completed_jobs:
        print("\nRecently completed jobs:")
        for job in completed_jobs[-5:]:  # Show last 5 completed jobs
            job_info = f"{job['file_name']}: Status {job.get('status', 'Unknown')}"
            if job.get("has_entities", False):
                job_info += f" (with {job.get('entity_count', 0)} entities)"
            print(f"  {job_info}")


def extract_entity_filenames_from_csv(csv_path: str) -> List[str]:
    """
    Extract entity filenames from a CSV file.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of entity filenames.
    """
    if not os.path.exists(csv_path):
        print(f"❌ File not found at: {csv_path}")
        return []

    try:
        df = pd.read_csv(csv_path)

        # Check if 'name' column exists
        if "name" in df.columns:
            entity_filenames = df["name"].tolist()
            print(
                f"Extracted {len(entity_filenames)} entity filenames from {os.path.basename(csv_path)}"
            )
            return entity_filenames
        else:
            print(f"Warning: 'name' column not found in {os.path.basename(csv_path)}")
            return []
    except Exception as e:
        print(f"Error reading {os.path.basename(csv_path)}: {str(e)}")
        return []


def load_entity_filenames_from_directory(
    ground_truth_dir: str,
) -> Tuple[Dict[str, List[str]], List[str]]:
    """
    Load entity filenames from all CSV files in a directory.

    Args:
        ground_truth_dir: Directory containing ground truth CSV files.

    Returns:
        Tuple containing:
        - Dictionary mapping file numbers to entity filenames
        - List of all entity filenames
    """
    # Get all ground truth CSV files
    csv_files = sorted(glob.glob(os.path.join(ground_truth_dir, "*.csv")))
    print(f"Found {len(csv_files)} ground truth CSV files in {ground_truth_dir}")

    # Read all CSV files and extract entity filenames
    entity_filenames_by_file = {}
    all_names = []

    for csv_file in csv_files:
        # Extract the file number from the CSV filename (e.g., 'nf_3.csv' -> '3')
        file_match = re.search(r"nf_(\d+)\.csv$", os.path.basename(csv_file))
        if file_match:
            file_num = file_match.group(1)

            names = extract_entity_filenames_from_csv(csv_file)

            # Store the names for this file number
            if names:
                entity_filenames_by_file[file_num] = names

                # Add to the list of all names
                all_names.extend(names)

    print(f"\nTotal unique entity filenames: {len(set(all_names))}")

    # Display a few examples
    if all_names:
        print("\nExample entity filenames:")
        for name in all_names[:5]:  # Show first 5 names
            print(f"  {name}")

    return entity_filenames_by_file, all_names


def map_files_to_entities(
    files: List[str],
    entity_filenames_by_file: Dict[str, List[str]],
    pattern: str = r"nf_(\d+)\.pdf$",
) -> Dict[str, List[str]]:
    """
    Map files to their corresponding entity filenames.

    Args:
        files: List of file paths.
        entity_filenames_by_file: Dictionary mapping file numbers to entity filenames.
        pattern: Regex pattern to extract file number from filename.

    Returns:
        Dictionary mapping file paths to entity filenames.
    """
    file_to_entities = {}

    for file in files:
        file_name = os.path.basename(file)
        file_match = re.search(pattern, file_name)

        if file_match:
            file_num = file_match.group(1)

            # Check if we have entity filenames for this file number
            if file_num in entity_filenames_by_file:
                file_to_entities[file] = entity_filenames_by_file[file_num]
                print(
                    f"Mapped {file_name} to {len(entity_filenames_by_file[file_num])} entity filenames"
                )
            else:
                print(f"Warning: No entity filenames found for {file_name}")

    print(f"\nMapped {len(file_to_entities)} files to their entity filenames")
    return file_to_entities


def analyze_batch_results(result: Dict[str, Any]) -> pd.DataFrame:
    """
    Analyze batch processing results.

    Args:
        result: Dictionary containing batch processing results.

    Returns:
        DataFrame containing job results.
    """
    # Convert results to DataFrame for analysis
    results_df = pd.DataFrame(result["jobs"])

    # Summary statistics
    print("\nStatus summary:")
    for status, count in result["status_counts"].items():
        print(f"{status}: {count} jobs")

    # Count files processed with entity filenames
    files_with_entities = [
        job for job in result["jobs"] if job.get("has_entities", False)
    ]
    print(f"\nFiles processed with entity filenames: {len(files_with_entities)}")

    # If there were failures, analyze the reasons
    if "FAILED" in result["status_counts"]:
        failed_jobs = [job for job in result["jobs"] if job.get("status") == "FAILED"]
        print("\nFailure reasons:")
        failure_reasons = {}
        for job in failed_jobs:
            reason = job.get("reason", "Unknown")
            if reason in failure_reasons:
                failure_reasons[reason] += 1
            else:
                failure_reasons[reason] = 1

        for reason, count in failure_reasons.items():
            print(f"  {reason}: {count} jobs")

    # If there were skipped files, analyze the reasons
    if "SKIPPED" in result["status_counts"]:
        skipped_jobs = [job for job in result["jobs"] if job.get("status") == "SKIPPED"]
        print("\nSkipped files reasons:")
        skip_reasons = {}
        for job in skipped_jobs:
            reason = job.get("reason", "Unknown")
            if reason in skip_reasons:
                skip_reasons[reason] += 1
            else:
                skip_reasons[reason] = 1

        for reason, count in skip_reasons.items():
            print(f"  {reason}: {count} jobs")

    # If there were timeouts, list them
    if "TIMEOUT" in result["status_counts"]:
        timeout_jobs = [job for job in result["jobs"] if job.get("status") == "TIMEOUT"]
        print("\nTimed out files:")
        for job in timeout_jobs:
            print(f"  {job['file_name']}")

    return results_df


def combine_batch_results(
    result: Dict[str, Any], output_file: str = "all_extracted_metadata.csv"
) -> Optional[pd.DataFrame]:
    """
    Combine all successful results from batch processing into a single DataFrame.

    Args:
        result: Dictionary containing batch processing results.
        output_file: Path to save the combined results.

    Returns:
        Combined DataFrame if successful, None otherwise.
    """
    # Combine all successful results into a single DataFrame
    completed_jobs = [
        job for job in result["jobs"] if job.get("status") in ["COMPLETED", "SUCCEEDED"]
    ]

    if len(completed_jobs) > 0:
        # Get all output files
        output_files = [
            job.get("output_file") for job in completed_jobs if job.get("output_file")
        ]

        if output_files:
            # Read and combine all CSV files
            all_data = []
            for file in output_files:
                try:
                    df = pd.read_csv(file)
                    # Add filename as a column to track source
                    df["source_file"] = os.path.basename(file)
                    # Add flag to indicate if processed with entities
                    file_name = os.path.basename(file)
                    job = next(
                        (j for j in completed_jobs if j.get("file_name") in file_name),
                        None,
                    )
                    if job:
                        df["processed_with_entities"] = job.get("has_entities", False)
                    all_data.append(df)
                except Exception as e:
                    print(f"Error reading {file}: {str(e)}")

            if all_data:
                # Combine all DataFrames
                combined_df = pd.concat(all_data, ignore_index=True)

                # Save combined results
                combined_df.to_csv(output_file, index=False)
                print(f"\nCombined {len(all_data)} result files into {output_file}")
                print(f"Total rows: {len(combined_df)}")

                return combined_df
            else:
                print("\nNo data could be read from the output files")
                return None
        else:
            print("\nNo output files available")
            return None
    else:
        print("\nNo successful results to combine")
        return None


def display_extraction_results(
    result: Dict[str, Any], entity_filenames: Optional[List[str]] = None
) -> None:
    """
    Display the results of metadata extraction.

    Args:
        result: Dictionary containing extraction results.
        entity_filenames: Optional list of entity filenames to check against results.
    """
    # Print the status first
    status = result.get("status", {})
    print(f"\nStatus: {status.get('status', 'UNKNOWN')}")

    # Check for output file and data
    if result.get("output_file") and "data" in result:
        print(f"\n✅ Metadata extracted to: {result['output_file']}")
        print("\nExtracted metadata preview:")
        display(result["data"].head())

        # Check if all entity filenames are in the results
        if (
            entity_filenames
            and "found_entities" in result
            and "missing_entities" in result
        ):
            print("\nEntities found in results:")
            for entity in entity_filenames:
                if entity in result["found_entities"]:
                    print(f"✅ {entity} - Found")
                else:
                    print(f"❌ {entity} - Not found")

            print(
                f"\nTotal entities found: {len(result['found_entities'])} of {len(entity_filenames)}"
            )
            print(f"Total entities missing: {len(result['missing_entities'])}")
    else:
        # Check if we have execution output with csvKey
        output_location = None
        if "status" in result and isinstance(result["status"], dict):
            if "outputLocation" in result["status"]:
                output_location = result["status"]["outputLocation"]
                print(f"\nOutput location found: {output_location}")
            elif result["status"].get("executionStatus", {}).get("output", {}).get(
                "bucket"
            ) and result["status"].get("executionStatus", {}).get("output", {}).get(
                "csvKey"
            ):
                bucket = result["status"]["executionStatus"]["output"]["bucket"]
                csv_key = result["status"]["executionStatus"]["output"]["csvKey"]
                output_location = f"s3://{bucket}/{csv_key}"
                print(
                    f"\nOutput location constructed from bucket and csvKey: {output_location}"
                )
                print(
                    f"To fix this issue, update the client to handle csvKey in the output."
                )

        if output_location:
            print(f"\n⚠️ Output location found but data not loaded: {output_location}")
            print(
                "This could be because the download failed or the data wasn't loaded into a DataFrame."
            )
        else:
            print("\n❌ Failed to extract metadata - No output location found")

        if "error" in result:
            print(f"Error: {result['error']}")

        # Print detailed status information for debugging
        print("\nDetailed status information:")
        if "status" in result and isinstance(result["status"], dict):
            if "executionStatus" in result["status"] and isinstance(
                result["status"]["executionStatus"], dict
            ):
                execution_output = result["status"]["executionStatus"].get("output", {})
                print(f"Execution output: {execution_output}")
