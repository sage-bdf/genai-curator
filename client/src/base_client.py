# This deliverable is considered developed content as defined in contract between BDF parties.


"""
Base client for interacting with the metadata API endpoints.

This module provides a base client class that handles common functionality
for all metadata API clients. The API follows an action-based structure:
/metadata/extract - For extracting metadata from documents
/metadata/fix - For fixing invalid values in metadata
/metadata/transform - For transforming metadata to match target schemas
/tasks/{executionArn} - For checking task status using the Step Functions execution ARN
"""

import json
import os
import time
from typing import Any, Callable, Dict, Optional

import requests


def raise_for_status_with_details(response: requests.Response) -> None:
    """
    Raise an HTTPError with detailed error information from the response body.

    Args:
        response: The response object to check.

    Raises:
        requests.exceptions.HTTPError: If the response status code indicates an error,
            with detailed error information from the response body.
    """
    if 400 <= response.status_code < 600:
        error_msg = f"{response.status_code} {response.reason} for url: {response.url}"

        # Try to extract error details from the response body
        try:
            # First try to parse as JSON
            error_details = response.json()
            if isinstance(error_details, dict):
                # Extract common error fields
                detail = (
                    error_details.get("detail")
                    or error_details.get("message")
                    or error_details.get("error")
                )
                if detail:
                    error_msg += f"\nError details: {detail}"
                else:
                    # If no specific error field found, include the whole response
                    error_msg += (
                        f"\nResponse body: {json.dumps(error_details, indent=2)}"
                    )
        except (ValueError, json.JSONDecodeError):
            # If not JSON, include the text content if available
            if response.text:
                # Limit the length to avoid extremely long error messages
                max_length = 500
                text = response.text[:max_length]
                if len(response.text) > max_length:
                    text += "... (truncated)"
                error_msg += f"\nResponse body: {text}"

        raise requests.HTTPError(error_msg, response=response)


class BaseClient:
    """
    Base client for interacting with the metadata API endpoints.

    This client handles authentication and provides common methods for interacting with
    the API endpoints.
    """

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize the base client.

        Args:
            api_url: The URL of the API. If not provided, will be read from the API_URL environment variable.
            api_key: The API key for authentication. If not provided, will be read from the API_KEY environment variable.
        """
        self.api_url = api_url or os.environ.get("API_URL")
        self.api_key = api_key or os.environ.get("API_KEY")

        if not self.api_url:
            raise ValueError(
                "API URL must be provided either as an argument or as the API_URL environment variable."
            )

        if not self.api_key:
            raise ValueError(
                "API key must be provided either as an argument or as the API_KEY environment variable."
            )

        self.headers = {"Content-Type": "application/json", "X-Api-Key": self.api_key}

    def upload_file(self, upload_url: str, file_path: str, content_type: str) -> None:
        """
        Upload a file to S3 using a presigned URL.

        Args:
            upload_url: The presigned URL to upload the file to.
            file_path: The path to the file to upload.
            content_type: The content type of the file.

        Raises:
            FileNotFoundError: If the file does not exist.
            requests.exceptions.RequestException: If the upload fails.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "rb") as file:
            response = requests.put(
                upload_url, data=file, headers={"Content-Type": content_type}
            )

        raise_for_status_with_details(response)

    def check_task_status(self, execution_arn: str) -> Dict[str, Any]:
        """
        Check the status of a task.

        Args:
            execution_arn: The execution ARN of the Step Functions execution to check.

        Returns:
            A dictionary containing the task status.

        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        # Use the execution ARN directly in the path parameter
        # This is URL-safe because the ARN is already properly formatted
        response = requests.get(
            f"{self.api_url}/tasks/{execution_arn}",
            headers=self.headers,
        )
        raise_for_status_with_details(response)
        return response.json()

    def poll_until_complete(
        self,
        execution_arn: str,
        max_attempts: int = 30,
        interval: int = 10,
        callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Poll for job status until completion or failure.

        Args:
            execution_arn: The execution ARN of the Step Functions execution to poll.
            max_attempts: The maximum number of attempts to check the status.
            interval: The interval in seconds between status checks.
            callback: Optional callback function to call with status updates.

        Returns:
            A dictionary containing the final task status.
        """
        attempts = 0
        while attempts < max_attempts:
            attempts += 1

            status_data = self.check_task_status(execution_arn)

            if callback:
                callback(status_data, attempts, max_attempts)

            # Check if job is complete
            if status_data.get("status") in ["COMPLETED", "FAILED", "SUCCEEDED"]:
                return status_data

            time.sleep(interval)

        return status_data
