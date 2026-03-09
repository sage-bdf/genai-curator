# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Extract Metadata Client for interacting with the metadata/extract API endpoint.

This module provides a client class for extracting metadata from documents.
It supports both uploading documents via presigned URLs and directly referencing
existing S3 objects.

Important Note: Generating a presigned URL and uploading a file does NOT automatically
start a job. The only way to start a job is by explicitly calling the metadata/extract
endpoint. This client handles this workflow automatically.
"""

import os
import time
from typing import Any, Callable, Dict, List, Optional

import boto3
import botocore
import pandas as pd
import requests

from base_client import BaseClient, raise_for_status_with_details
from utils import default_status_callback, download_results, get_file_info


class ExtractMetadataClient(BaseClient):
    """
    Client for extracting metadata from documents.

    This client provides methods for extracting metadata from documents using
    the extract_metadata API endpoint. It handles the complete workflow for both
    S3 and local files:

    1. For S3 files: Directly calls the extract_metadata API endpoint
    2. For local files: Uploads the file using a presigned URL, then calls the
       extract_metadata API endpoint to start the job

    Note: The client automatically handles the two-step process for local files,
    ensuring that jobs are properly started after upload.
    """

    def _check_s3_object_exists(self, bucket: str, key: str) -> bool:
        """
        Check if an object exists in S3.

        Args:
            bucket: The S3 bucket name
            key: The S3 object key

        Returns:
            True if the object exists, False otherwise
        """
        s3_client = boto3.client("s3")
        try:
            s3_client.head_object(Bucket=bucket, Key=key)
            return True
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            else:
                # Re-raise the exception for other errors
                raise

    def extract_metadata_from_s3(
        self,
        bucket: str,
        document_key: str,
        schema_key: str,
        output_prefix: str,
        filenames: Optional[list[str]] = None,
        max_attempts: int = 30,
        interval: int = 10,
        output_path: Optional[str] = None,
        callback: Optional[Callable] = None,
        skip_existence_check: bool = False,
    ) -> dict[str, Any]:
        """
        Extract metadata from a document in S3.

        This method directly calls the extract_metadata API endpoint with the S3 location.

        Args:
            bucket: The S3 bucket containing the document
            document_key: The S3 key of the document
            schema_key: The S3 key of the schema file
            output_prefix: The S3 prefix where output files will be written
            filenames: Optional list of entity filenames to extract metadata for
            max_attempts: The maximum number of attempts to check the status
            interval: The interval in seconds between status checks
            output_path: The path to save the extracted metadata to
            callback: Optional callback function to call with status updates
            skip_existence_check: If True, skip checking if files exist in S3

        Returns:
            A dictionary containing the final task status and the path to the extracted metadata.

        Raises:
            FileNotFoundError: If the document or schema file does not exist in S3
        """
        # Check if the document and schema files exist in S3
        if not skip_existence_check:
            missing_files = []

            if not self._check_s3_object_exists(bucket, document_key):
                missing_files.append(f"Document: s3://{bucket}/{document_key}")

            if not self._check_s3_object_exists(bucket, schema_key):
                missing_files.append(f"Schema: s3://{bucket}/{schema_key}")

            if missing_files:
                raise FileNotFoundError(
                    f"The following files do not exist in S3: {', '.join(missing_files)}"
                )

        # Prepare payload for S3 source
        payload = {
            "bucket": bucket,
            "document_key": document_key,
            "schema_key": schema_key,
            "output_prefix": output_prefix,
        }

        # Add filenames if provided
        if filenames:
            payload["filenames"] = filenames

        # Call the API endpoint
        response = requests.post(
            f"{self.api_url}/metadata/extract",
            headers=self.headers,
            json=payload,
            timeout=10,
        )
        raise_for_status_with_details(response)
        result = response.json()

        execution_arn = result.get("executionArn")
        if not execution_arn:
            raise ValueError("No execution ARN returned from API")

        # Poll for completion and process results
        return self._process_execution_results(
            execution_arn=execution_arn,
            max_attempts=max_attempts,
            interval=interval,
            callback=callback,
            output_path=output_path,
            document_name=os.path.basename(document_key),
        )

    def extract_metadata_from_local(
        self,
        file_path: str,
        schema_name: str,
        schema_key: str,
        filenames: Optional[list[str]] = None,
        max_attempts: int = 30,
        interval: int = 10,
        output_path: Optional[str] = None,
        callback: Optional[Callable] = None,
    ) -> dict[str, Any]:
        """
        Extract metadata from a local document file.

        This method uploads the file using a presigned URL, then calls the extract_metadata
        API endpoint to start the job.

        Args:
            file_path: The path to the local document
            schema_name: The schema name to use
            schema_key: The S3 key of the schema file
            filenames: Optional list of entity filenames to extract metadata for
            max_attempts: The maximum number of attempts to check the status
            interval: The interval in seconds between status checks
            output_path: The path to save the extracted metadata to
            callback: Optional callback function to call with status updates

        Returns:
            A dictionary containing the final task status and the path to the extracted metadata.
        """
        # Get file info
        file_info = get_file_info(file_path)

        # Request presigned URL
        payload = {
            "schemaName": schema_name,
            "fileType": file_info["mime_type"],
            "fileExtension": file_info["file_extension"],
            "workflow": "extract_metadata",
        }

        # Add filenames if provided
        if filenames:
            payload["filenames"] = filenames

        # Use the metadata/extract/upload endpoint
        response = requests.post(
            f"{self.api_url}/metadata/extract/upload",
            headers=self.headers,
            json=payload,
            timeout=10,
        )
        raise_for_status_with_details(response)
        upload_info = response.json()

        job_id = upload_info["jobId"]
        upload_url = upload_info["uploadUrl"]

        # Get bucket and key from the response
        s3_bucket = upload_info["bucket"]
        s3_key = upload_info["key"]

        # Upload file
        self.upload_file(upload_url, file_path, file_info["mime_type"])

        # Construct output prefix from job ID
        output_prefix = f"extract_metadata/{schema_name}/jobs/{job_id}"

        # Check if schema file exists in S3
        if not self._check_s3_object_exists(s3_bucket, schema_key):
            raise FileNotFoundError(
                f"Schema file does not exist: s3://{s3_bucket}/{schema_key}"
            )

        # Call the extract_metadata endpoint to start the job
        extract_payload = {
            "bucket": s3_bucket,
            "document_key": s3_key,
            "schema_key": schema_key,
            "output_prefix": output_prefix,
        }

        # Add filenames if provided
        if filenames:
            extract_payload["filenames"] = filenames

        # Call the API endpoint to start the job
        extract_response = requests.post(
            f"{self.api_url}/metadata/extract",
            headers=self.headers,
            json=extract_payload,
            timeout=10,
        )

        raise_for_status_with_details(extract_response)
        extract_result = extract_response.json()

        execution_arn = extract_result.get("executionArn")
        if not execution_arn:
            raise ValueError("No execution ARN returned from API")

        # Poll for completion and process results
        return self._process_execution_results(
            execution_arn=execution_arn,
            max_attempts=max_attempts,
            interval=interval,
            callback=callback,
            output_path=output_path,
            document_name=os.path.splitext(file_info["file_name"])[0],
            file_info=file_info,
        )

    def extract_metadata(
        self,
        source: str = None,
        bucket: str = None,
        document_key: str = None,
        schema_key: str = None,
        output_prefix: str = None,
        file_path: str = None,
        schema_name: str = None,
        filenames: Optional[list[str]] = None,
        max_attempts: int = 30,
        interval: int = 10,
        output_path: Optional[str] = None,
        callback: Optional[Callable] = None,
        skip_existence_check: bool = False,
    ) -> dict[str, Any]:
        """
        Extract metadata from a document in S3 or from a local file.

        This method is a facade that routes to either extract_metadata_from_s3 or
        extract_metadata_from_local based on the source parameter.

        Args:
            source: Source type, either 's3' or 'local'. If not provided, will be inferred from other parameters.
            bucket: The S3 bucket containing the document (required if source is 's3')
            document_key: The S3 key of the document (required if source is 's3')
            schema_key: The S3 key of the schema file (required for both sources)
            output_prefix: The S3 prefix where output files will be written (required if source is 's3')
            file_path: The path to the local document (required if source is 'local')
            schema_name: The schema name to use (required if source is 'local')
            filenames: Optional list of entity filenames to extract metadata for
            max_attempts: The maximum number of attempts to check the status
            interval: The interval in seconds between status checks
            output_path: The path to save the extracted metadata to
            callback: Optional callback function to call with status updates
            skip_existence_check: If True, skip checking if files exist in S3 (only applies to S3 source)

        Returns:
            A dictionary containing the final task status and the path to the extracted metadata.
        """
        # Infer source if not provided
        if source is None:
            if bucket is not None and document_key is not None:
                source = "s3"
            elif file_path is not None:
                source = "local"
            else:
                raise ValueError(
                    "Either (bucket and document_key) or file_path must be provided"
                )

        if source == "s3":
            if not bucket or not document_key or not schema_key or not output_prefix:
                raise ValueError(
                    "'bucket', 'document_key', 'schema_key', and 'output_prefix' are required for S3 source"
                )

            return self.extract_metadata_from_s3(
                bucket=bucket,
                document_key=document_key,
                schema_key=schema_key,
                output_prefix=output_prefix,
                filenames=filenames,
                max_attempts=max_attempts,
                interval=interval,
                output_path=output_path,
                callback=callback,
                skip_existence_check=skip_existence_check,
            )
        elif source == "local":
            if not file_path or not schema_name or not schema_key:
                raise ValueError(
                    "'file_path', 'schema_name', and 'schema_key' are required for local source"
                )

            return self.extract_metadata_from_local(
                file_path=file_path,
                schema_name=schema_name,
                schema_key=schema_key,
                filenames=filenames,
                max_attempts=max_attempts,
                interval=interval,
                output_path=output_path,
                callback=callback,
            )
        else:
            raise ValueError("Source must be either 's3' or 'local'")

    def _process_execution_results(
        self,
        execution_arn: str,
        max_attempts: int,
        interval: int,
        callback: Optional[Callable],
        output_path: Optional[str],
        document_name: str,
        file_info: Optional[Dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Process the results of a Step Functions execution.

        This method polls for completion, downloads results if available, and returns
        a dictionary with the final status and output information.

        Args:
            execution_arn: The execution ARN to poll
            max_attempts: The maximum number of attempts to check the status
            interval: The interval in seconds between status checks
            callback: Optional callback function to call with status updates
            output_path: The path to save the extracted metadata to
            document_name: The name of the document (used for default output file naming)
            file_info: Optional file info dictionary for local files

        Returns:
            A dictionary containing the final task status and the path to the extracted metadata.
        """
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
            output_file = output_path or f"extracted_metadata_{document_name}.csv"
            result["output_file"] = download_results(output_location, output_file)

            # Load the results into a DataFrame if available
            if result["output_file"] and os.path.exists(result["output_file"]):
                try:
                    result["data"] = pd.read_csv(result["output_file"])

                    # Check if all entity filenames are in the results
                    if "filenames" in final_status and "name" in result["data"].columns:
                        filenames = final_status["filenames"]
                        found_entities = result["data"]["name"].tolist()
                        result["found_entities"] = [
                            entity for entity in filenames if entity in found_entities
                        ]
                        result["missing_entities"] = [
                            entity
                            for entity in filenames
                            if entity not in found_entities
                        ]
                except Exception as e:
                    result["error"] = f"Error reading results: {str(e)}"

        return result

    def extract_metadata_with_entities(
        self,
        file_path: str,
        schema_name: str,
        schema_key: str,
        entity_filenames: list[str],
        max_attempts: int = 30,
        interval: int = 10,
        output_path: Optional[str] = None,
        callback: Optional[Callable] = None,
    ) -> dict[str, Any]:
        """
        Extract metadata from a document with entity filenames.

        DEPRECATED: This is a legacy method that calls the consolidated extract_metadata method.
        Use extract_metadata directly with source='local' instead.

        Args:
            file_path: The path to the document.
            schema_name: The name of the schema to use for extraction.
            schema_key: The S3 key of the schema file.
            entity_filenames: A list of entity filenames to extract metadata for.
            max_attempts: The maximum number of attempts to check the status.
            interval: The interval in seconds between status checks.
            output_path: The path to save the extracted metadata to. If None, a default path will be used.
            callback: Optional callback function to call with status updates.

        Returns:
            A dictionary containing the final task status and the path to the extracted metadata.
        """
        return self.extract_metadata_from_local(
            file_path=file_path,
            schema_name=schema_name,
            schema_key=schema_key,
            filenames=entity_filenames,
            max_attempts=max_attempts,
            interval=interval,
            output_path=output_path,
            callback=callback,
        )

    def process_files(
        self,
        files: List[str],
        schema_name: str,
        schema_key: str,
        file_to_entities: Optional[dict[str, list[str]]] = None,
        skip_extensions: Optional[List[str]] = None,
        max_workers: int = 5,
        poll_interval: int = 10,
        max_time: int = 1800,
        download_results_flag: bool = True,
        output_dir: Optional[str] = None,
        callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Process multiple files in parallel.

        This method handles the complete workflow for each file:
        1. Uploads the file using a presigned URL
        2. Explicitly calls the extract_metadata endpoint to start the job
        3. Monitors job status until completion
        4. Downloads results if requested

        Args:
            files: A list of file paths to process.
            schema_name: The name of the schema to use for extraction.
            schema_key: The S3 key of the schema file.
            file_to_entities: Optional dictionary mapping file paths to lists of entity filenames.
            skip_extensions: A list of file extensions to skip.
            max_workers: Maximum number of worker threads for parallel processing.
            poll_interval: Time in seconds between status checks.
            max_time: Maximum time in seconds to wait for all jobs.
            download_results_flag: Whether to download results for completed jobs.
            output_dir: Directory to save results to. If None, results will be saved in the current directory.
            callback: Optional callback function to call with status updates.

        Returns:
            A dictionary containing the results of the batch processing.
        """
        from concurrent.futures import ThreadPoolExecutor

        # Initialize file_to_entities if not provided
        if file_to_entities is None:
            file_to_entities = {}

        # Start all jobs in parallel
        jobs = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(
                    self._start_processing_job,
                    file_path,
                    schema_name,
                    schema_key,
                    skip_extensions,
                    file_to_entities.get(file_path),
                ): file_path
                for file_path in files
            }

            for future in future_to_file:
                try:
                    job_info = future.result()
                    if job_info:
                        jobs.append(job_info)
                except Exception as e:
                    file_path = future_to_file[future]
                    jobs.append(
                        {
                            "file_name": os.path.basename(file_path),
                            "file_path": file_path,
                            "status": "FAILED",
                            "reason": str(e),
                        }
                    )

        # Monitor job status
        results = self._monitor_jobs(jobs, poll_interval, max_time, callback)

        # Download results for completed jobs if requested
        if download_results_flag:
            for job in results:
                if (
                    job.get("status") in ["COMPLETED", "SUCCEEDED"]
                    and "output_location" in job
                ):
                    output_file = os.path.join(
                        output_dir or "",
                        f"extracted_metadata_{os.path.splitext(job['file_name'])[0]}.csv",
                    )
                    job["output_file"] = download_results(
                        job["output_location"], output_file
                    )

        # Summarize results
        status_counts = {}
        for job in results:
            status = job.get("status")
            if status in status_counts:
                status_counts[status] += 1
            else:
                status_counts[status] = 1

        return {
            "jobs": results,
            "status_counts": status_counts,
            "total_files": len(files),
            "processed_files": len(results),
        }

    def _start_processing_job(
        self,
        file_path: str,
        schema_name: str,
        schema_key: str,
        skip_extensions: Optional[List[str]] = None,
        filenames: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Start processing a file and return job info without waiting for completion.

        This method uploads the file using a presigned URL and then calls the extract_metadata
        endpoint to start the job. The job ID from the extract_metadata response is used for monitoring.

        Args:
            file_path: The path to the file to process.
            schema_name: The name of the schema to use for extraction.
            schema_key: The S3 key of the schema file.
            skip_extensions: A list of file extensions to skip.
            filenames: Optional list of entity filenames to extract metadata for.

        Returns:
            A dictionary containing job information.
        """
        file_info = get_file_info(file_path)
        file_name = file_info["file_name"]

        # Skip files with specified extensions
        if skip_extensions and any(file_path.endswith(ext) for ext in skip_extensions):
            return {
                "file_name": file_name,
                "file_path": file_path,
                "status": "SKIPPED",
                "reason": f"File extension in skip list: {os.path.splitext(file_path)[1]}",
            }

        try:
            # Request presigned URL using the upload endpoint
            payload = {
                "schemaName": schema_name,
                "fileType": file_info["mime_type"],
                "fileExtension": file_info["file_extension"],
                "workflow": "extract_metadata",  # Add workflow parameter
            }

            # Add filenames if provided
            if filenames:
                payload["filenames"] = filenames

            # Use the metadata/extract/upload endpoint
            response = requests.post(
                f"{self.api_url}/metadata/extract/upload",
                headers=self.headers,
                json=payload,
                timeout=10,
            )

            raise_for_status_with_details(response)
            upload_info = response.json()

            job_id = upload_info["jobId"]
            upload_url = upload_info["uploadUrl"]

            # Get bucket and key from the response
            s3_bucket = upload_info["bucket"]
            s3_key = upload_info["key"]

            # Upload file
            self.upload_file(upload_url, file_path, file_info["mime_type"])

            # Check if schema file exists in S3
            if not self._check_s3_object_exists(s3_bucket, schema_key):
                raise FileNotFoundError(
                    f"Schema file does not exist: s3://{s3_bucket}/{schema_key}"
                )

            # Construct output prefix from job ID
            output_prefix = f"extract_metadata/{schema_name}/jobs/{job_id}"

            # Call the extract_metadata endpoint to start the job
            extract_payload = {
                "bucket": s3_bucket,
                "document_key": s3_key,
                "schema_key": schema_key,
                "output_prefix": output_prefix,
            }

            # Add filenames if provided
            if filenames:
                extract_payload["filenames"] = filenames

            # Call the API endpoint to start the job
            extract_response = requests.post(
                f"{self.api_url}/metadata/extract",
                headers=self.headers,
                json=extract_payload,
            )

            raise_for_status_with_details(extract_response)
            extract_result = extract_response.json()

            execution_arn = extract_result.get("executionArn")
            if not execution_arn:
                raise ValueError("No execution ARN returned from API")

            # Return job info for monitoring
            job_info = {
                "file_name": file_name,
                "file_path": file_path,
                "execution_arn": execution_arn,  # Store execution ARN for monitoring
                "status": "STARTED",
                "start_time": time.time(),
            }

            # Add entity info if available
            if filenames:
                job_info["has_entities"] = True
                job_info["entity_count"] = len(filenames)

            return job_info
        except Exception as e:
            return {
                "file_name": file_name,
                "file_path": file_path,
                "status": "FAILED",
                "reason": str(e),
            }

    def _monitor_jobs(
        self,
        jobs: List[Dict[str, Any]],
        poll_interval: int = 10,
        max_time: int = 1800,
        callback: Optional[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        Monitor the status of multiple jobs and update their status.

        Args:
            jobs: List of job info dictionaries.
            poll_interval: Time in seconds between status checks.
            max_time: Maximum time in seconds to wait for all jobs.
            callback: Optional callback function to call with status updates.

        Returns:
            Updated list of job info dictionaries.
        """
        import time

        start_time = time.time()
        active_jobs = [job for job in jobs if job.get("status") == "STARTED"]
        completed_jobs = [job for job in jobs if job.get("status") != "STARTED"]

        while active_jobs and (time.time() - start_time) < max_time:
            if callback:
                callback(active_jobs, completed_jobs)

            still_active = []
            for job in active_jobs:
                execution_arn = job.get("execution_arn")

                if not execution_arn:
                    job["status"] = "FAILED"
                    job["reason"] = "Missing execution ARN"
                    completed_jobs.append(job)
                    continue

                try:
                    status_data = self.check_task_status(execution_arn)
                    job_status = status_data.get("status")

                    if job_status in ["COMPLETED", "FAILED", "SUCCEEDED"]:
                        job["status"] = job_status

                        # Check for outputLocation at the top level or construct it from output.bucket and output.csvKey
                        if job_status in ["COMPLETED", "SUCCEEDED"]:
                            if "outputLocation" in status_data:
                                job["output_location"] = status_data["outputLocation"]
                            elif status_data.get("executionStatus", {}).get(
                                "output", {}
                            ).get("bucket") and status_data.get(
                                "executionStatus", {}
                            ).get(
                                "output", {}
                            ).get(
                                "csvKey"
                            ):
                                # Construct outputLocation from bucket and csvKey
                                bucket = status_data["executionStatus"]["output"][
                                    "bucket"
                                ]
                                csv_key = status_data["executionStatus"]["output"][
                                    "csvKey"
                                ]
                                job["output_location"] = f"s3://{bucket}/{csv_key}"
                        elif job_status == "FAILED":
                            job["reason"] = "Job failed according to status check"

                        completed_jobs.append(job)
                    else:
                        still_active.append(job)
                except Exception as e:
                    # Keep job active if we couldn't get status
                    job["last_error"] = str(e)
                    still_active.append(job)

            active_jobs = still_active

            if active_jobs:
                time.sleep(poll_interval)

        # Handle any remaining active jobs that timed out
        for job in active_jobs:
            job["status"] = "TIMEOUT"
            job["reason"] = f"Job did not complete within {max_time} seconds"
            completed_jobs.append(job)

        return completed_jobs
