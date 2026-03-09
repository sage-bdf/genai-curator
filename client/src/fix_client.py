# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Fix Metadata Client for interacting with the metadata/fix API endpoint.

This module provides a client class for fixing invalid values in tabular data.
"""

import os
import time
from typing import Any, Callable, Dict, Optional

import pandas as pd
import requests

from base_client import BaseClient, raise_for_status_with_details
from utils import download_results, get_file_info


class FixMetadataClient(BaseClient):
    """Client for fixing invalid values in tabular data.

    This client provides methods for fixing invalid values in tabular data using
    the metadata/fix API endpoint.
    """

    def fix_metadata(
        self,
        file_path: str,
        schema_name: str,
        output_path: Optional[str] = None,
        callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Fix invalid values in tabular data using AI-powered corrections.

        Args:
            file_path: The path to the CSV file with invalid values.
            schema_name: The name of the schema to use for validation.
            output_path: The path to save the corrected data to. If None, a default path will be used.
            callback: Optional callback function to call with status updates.

        Returns:
            A dictionary containing the results and the path to the corrected data.
        """
        # Get file info
        file_info = get_file_info(file_path)

        # Request presigned URL using the dedicated endpoint
        payload = {
            "schemaName": schema_name,
            "fileType": "text/csv",
            "fileExtension": "csv",
            "workflow": "fix_metadata",
        }

        # Use the metadata/fix/upload endpoint
        response = requests.post(
            f"{self.api_url}/metadata/fix/upload",
            headers=self.headers,
            json=payload,
            timeout=10,
        )

        raise_for_status_with_details(response)
        upload_info = response.json()

        job_id = upload_info["jobId"]
        upload_url = upload_info["uploadUrl"]

        # Upload file
        self.upload_file(upload_url, file_path, "text/csv")

        # Determine the bucket name from the upload URL
        # The URL format is typically: https://<bucket>.s3.<region>.amazonaws.com/<key>...
        bucket_name = upload_url.split("//")[1].split(".")[0]

        # Call the fix_metadata endpoint to start the job with the new API format
        fix_payload = {
            "sourceTablePath": f"s3://{bucket_name}/fix_metadata/{schema_name}/jobs/{job_id}/input.csv",
            "outputPrefix": job_id,
            "schemaKey": f"fix_metadata/{schema_name}/schema.json",
            "workflow": "fix_metadata",
        }

        # If callback is provided, call it with initial status
        if callback:
            callback(
                {"status": "STARTING", "message": "Uploading file and starting job"}
            )

        # Call the API endpoint to start the job
        fix_response = requests.post(
            f"{self.api_url}/metadata/fix",
            headers=self.headers,
            json=fix_payload,
            timeout=30,  # Reduced timeout since we're now using async Step Function
        )
        raise_for_status_with_details(fix_response)
        fix_result = fix_response.json()

        # Get the execution ARN from the response
        execution_arn = fix_result.get("executionArn")
        if not execution_arn:
            raise ValueError("No execution ARN returned from the API")

        # If callback is provided, call it with initial status
        if callback:
            callback(
                {
                    "status": "PROCESSING",
                    "message": "Job started, waiting for completion",
                    "executionArn": execution_arn,
                }
            )

        # Poll the task status endpoint until the job is complete
        max_retries = (
            60  # Maximum number of retries (10 minutes with 10-second intervals)
        )
        retry_interval = 10  # Seconds between retries

        for i in range(max_retries):
            # Call the task status endpoint
            status_response = requests.get(
                f"{self.api_url}/tasks/{execution_arn}",
                headers=self.headers,
                timeout=10,
            )
            raise_for_status_with_details(status_response)
            status_result = status_response.json()

            # Check if the job is complete
            status = status_result.get("status")

            # If callback is provided, call it with current status
            if callback:
                callback(
                    {
                        "status": status,
                        "message": f"Job status: {status}",
                        "details": status_result,
                    }
                )

            if status == "COMPLETED":
                break
            elif status == "FAILED":
                raise ValueError(f"Job failed: {status_result}")

            # Wait before retrying
            if i < max_retries - 1:  # Don't sleep on the last iteration
                time.sleep(retry_interval)

        # If we've exhausted all retries and the job is still not complete, raise an error
        if status != "COMPLETED":
            raise TimeoutError(
                f"Job did not complete within the expected time. Current status: {status}"
            )

        # Get the output location from the status response
        output_location = status_result.get("outputLocation")
        if not output_location:
            # Try to get it from the execution status output
            execution_status = status_result.get("executionStatus", {})
            output = execution_status.get("output", {})
            if isinstance(output, dict):
                corrected_csv_uri = output.get("correctedCsvS3Uri")
            else:
                corrected_csv_uri = None
        else:
            corrected_csv_uri = output_location

        # If callback is provided, call it with completion status
        if callback:
            callback({"status": "COMPLETED", "message": "Job completed successfully"})

        # Process the results
        result = {"status": "COMPLETED", "raw_response": status_result}
        if corrected_csv_uri:
            output_file = (
                output_path
                or f"fixed_metadata_{os.path.splitext(file_info['file_name'])[0]}.csv"
            )
            result["output_file"] = download_results(corrected_csv_uri, output_file)

            # Load the results into a DataFrame if available
            if result["output_file"] and os.path.exists(result["output_file"]):
                try:
                    result["data"] = pd.read_csv(result["output_file"])

                    # Compare with original data to identify corrections
                    try:
                        original_data = pd.read_csv(file_path)

                        # Check if the shapes match
                        if original_data.shape == result["data"].shape:
                            # Find differences between original and corrected data
                            differences = {}

                            for column in original_data.columns:
                                if column in result["data"].columns:
                                    # Find rows where values differ
                                    diff_mask = (
                                        original_data[column] != result["data"][column]
                                    )
                                    if diff_mask.any():
                                        differences[column] = {
                                            "count": diff_mask.sum(),
                                            "examples": [
                                                {
                                                    "row": i,
                                                    "original": original_data.loc[
                                                        i, column
                                                    ],
                                                    "corrected": result["data"].loc[
                                                        i, column
                                                    ],
                                                }
                                                for i in diff_mask[diff_mask].index[
                                                    :5
                                                ]  # Show up to 5 examples
                                            ],
                                        }

                            result["corrections"] = differences
                            result["correction_count"] = sum(
                                diff["count"] for diff in differences.values()
                            )
                    except Exception as e:
                        result["comparison_error"] = (
                            f"Error comparing with original data: {str(e)}"
                        )
                except Exception as e:
                    result["error"] = f"Error reading results: {str(e)}"

        return result
