# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Transform Metadata Client for interacting with the metadata/transform API endpoint.

This module provides a client class for transforming tables to match target schemas.
It follows the same pattern as the metadata/extract client, where files are uploaded
via presigned URLs and then the workflow is explicitly started via the API.
"""

import os
from typing import Any, Callable, Dict, Optional

import pandas as pd
import requests

from base_client import BaseClient, raise_for_status_with_details
from utils import default_status_callback, download_results, get_file_info


class TransformMetadataClient(BaseClient):
    """
    Client for transforming tables to match target schemas.

    This client provides methods for transforming tables to match target schemas using
    the metadata/transform API endpoint.
    """

    def transform_metadata(
        self,
        file_path: str,
        schema_name: str,
        max_attempts: int = 30,
        interval: int = 10,
        output_path: Optional[str] = None,
        callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Transform tables to match target schemas using AI-powered column translation.

        Args:
            file_path: The path to the source CSV file.
            schema_name: The name of the target schema.
            max_attempts: The maximum number of attempts to check the status.
            interval: The interval in seconds between status checks.
            output_path: The path to save the transformed data to. If None, a default path will be used.
            callback: Optional callback function to call with status updates.

        Returns:
            A dictionary containing the final task status and the path to the transformed data.
        """
        # Get file info
        file_info = get_file_info(file_path)

        # Request presigned URL using the dedicated endpoint
        payload = {
            "schemaName": schema_name,
            "fileType": file_info["mime_type"],
            "fileExtension": file_info["file_extension"],
            "workflow": "transform_metadata",
        }

        # Use the metadata/transform/upload endpoint
        response = requests.post(
            f"{self.api_url}/metadata/transform/upload",
            headers=self.headers,
            json=payload,
            timeout=10,
        )

        raise_for_status_with_details(response)
        upload_info = response.json()

        job_id = upload_info["jobId"]
        upload_url = upload_info["uploadUrl"]

        # Upload file
        self.upload_file(upload_url, file_path, file_info["mime_type"])

        # After uploading, we need to explicitly call the transform_metadata endpoint
        # to start the job, as uploading via presigned URL doesn't automatically trigger it
        s3_key = f"transform_metadata/{schema_name}/jobs/{job_id}/input.{file_info['file_extension']}"

        # Determine the bucket name from the upload URL
        # The URL format is typically: https://<bucket>.s3.<region>.amazonaws.com/<key>...
        bucket_name = upload_url.split("//")[1].split(".")[0]

        # Call the transform_metadata endpoint to start the job
        transform_payload = {
            "bucket": bucket_name,
            "key": s3_key,
            "jobId": job_id,
            "workflow": "transform_metadata",
        }

        # Call the API endpoint to start the job
        transform_response = requests.post(
            f"{self.api_url}/metadata/transform",
            headers=self.headers,
            json=transform_payload,
            timeout=10,
        )

        raise_for_status_with_details(transform_response)
        transform_result = transform_response.json()

        execution_arn = transform_result.get("executionArn")
        if not execution_arn:
            raise ValueError("No execution ARN returned from API")

        # Poll for completion
        callback_fn = callback or default_status_callback
        final_status = self.poll_until_complete(
            execution_arn, max_attempts, interval, callback_fn
        )

        # Download results if available
        result = {"status": final_status}

        # Check for outputLocation at the top level or construct it from output.bucket and output.csvKey
        output_location = None
        if "outputLocation" in final_status:
            output_location = final_status["outputLocation"]
        elif final_status.get("executionStatus", {}).get("output", {}).get(
            "bucket"
        ) and final_status.get("executionStatus", {}).get("output", {}).get("csvKey"):
            # Construct outputLocation from bucket and csvKey
            bucket = final_status["executionStatus"]["output"]["bucket"]
            csv_key = final_status["executionStatus"]["output"]["csvKey"]
            output_location = f"s3://{bucket}/{csv_key}"

        if final_status.get("status") in ["COMPLETED", "SUCCEEDED"] and output_location:
            output_file = (
                output_path
                or f"transformed_metadata_{os.path.splitext(file_info['file_name'])[0]}.csv"
            )
            result["output_file"] = download_results(output_location, output_file)

            # Load the results into a DataFrame if available
            if result["output_file"] and os.path.exists(result["output_file"]):
                try:
                    result["data"] = pd.read_csv(result["output_file"])

                    # Extract transformation details if available
                    if "transformationDetails" in final_status:
                        result["transformation_details"] = final_status[
                            "transformationDetails"
                        ]

                    # Compare with original data to understand transformations
                    try:
                        original_data = pd.read_csv(file_path)

                        # Analyze column mappings
                        original_columns = set(original_data.columns)
                        transformed_columns = set(result["data"].columns)

                        result["column_analysis"] = {
                            "original_columns": list(original_columns),
                            "transformed_columns": list(transformed_columns),
                            "added_columns": list(
                                transformed_columns - original_columns
                            ),
                            "removed_columns": list(
                                original_columns - transformed_columns
                            ),
                            "preserved_columns": list(
                                original_columns & transformed_columns
                            ),
                        }

                        # Check if row count is preserved
                        result["row_count"] = {
                            "original": len(original_data),
                            "transformed": len(result["data"]),
                            "preserved": len(original_data) == len(result["data"]),
                        }
                    except Exception as e:
                        result["comparison_error"] = (
                            f"Error comparing with original data: {str(e)}"
                        )
                except Exception as e:
                    result["error"] = f"Error reading results: {str(e)}"

        return result
