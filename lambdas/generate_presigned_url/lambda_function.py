# This deliverable is considered developed content as defined in contract between BDF parties.


"""Lambda function that generates a pre-signed URL for file uploads.

This module provides an API endpoint to generate pre-signed URLs for uploading files to S3.
It creates a unique job ID, determines the appropriate S3 key based on the workflow type,
and returns a pre-signed URL along with the job ID, bucket, key, and expiration time.
"""

import datetime
import json
import os
import uuid

import boto3
from aws_lambda_powertools import Logger

# Configure logging with Lambda Powertools
logger = Logger(service="generate_presigned_url")

# Initialize AWS clients
s3_client = boto3.client("s3")

# Environment variables
S3_BUCKET = os.environ["S3_BUCKET"]
EXPIRATION = 3600  # 1 hour


def lambda_handler(event, context):
    """Generate a pre-signed URL for uploading a file to S3.

    This function creates a unique job ID, determines the appropriate S3 key based on
    the workflow type, and returns a pre-signed URL along with the job ID, bucket, key, and expiration time.

    Args:
        event: API Gateway event containing the workflow type and file type
        context: Lambda context object

    Returns:
        JSON response with job ID, bucket, key, pre-signed URL, and expiration time
    """
    logger.info(f"event: {event}")

    try:
        # Parse request body
        body = event.get("body", json.dumps({}))
        if isinstance(body, str):
            body = json.loads(body)

        # Extract parameters from the request
        workflow_name = body.get("workflow", None)
        schema_name = body.get("schemaName", None)
        file_type = body.get("fileType", "application/zip")
        file_extension = body.get("fileExtension", "zip")
        entity_filenames = body.get("entityFilenames", None)

        # Validate required parameters (client-side validation)
        if workflow_name is None:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "'workflow' arg not provided"}),
            }
        if schema_name is None:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "'schemaName' arg not provided"}),
            }

        # Validate workflow name
        valid_workflows = ["extract_metadata", "fix_metadata", "transform_metadata"]
        if workflow_name not in valid_workflows:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {
                        "error": f"Invalid workflow name: {workflow_name}. Must be one of: {valid_workflows}"
                    }
                ),
            }

        if workflow_name == "transform_metadata":
            extensions = [".csv", ".tsv"]
            schema_found = False
            for ext in extensions:
                schema_file_key = f"{workflow_name}/schema/{schema_name}{ext}"
                try:
                    s3_client.head_object(Bucket=S3_BUCKET, Key=schema_file_key)
                    schema_found = True
                    break
                except s3_client.exceptions.ClientError:
                    continue
            if not schema_found:
                return {
                    "statusCode": 404,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(
                        {
                            "error": f"Schema file not found. Tried: {[f'{schema_name}{ext}' for ext in extensions]}"
                        }
                    ),
                }
        else:
            # Check if schema file exists in S3
            schema_file_key = f"{workflow_name}/{schema_name}/schema.json"
            try:
                s3_client.head_object(Bucket=S3_BUCKET, Key=schema_file_key)
            except s3_client.exceptions.ClientError:
                return {
                    "statusCode": 404,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(
                        {"error": f"Schema file not found at {schema_file_key}"}
                    ),
                }

        # Generate a unique job ID with timestamp prefix and shortened UUID
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        short_uuid = str(uuid.uuid4()).split("-")[0]  # Use only the first 8 characters
        job_id = f"{timestamp}-{short_uuid}"

        # Define the S3 key where the file will be uploaded
        s3_key = f"{workflow_name}/{schema_name}/jobs/{job_id}/input.{file_extension}"

        # Generate a pre-signed URL for uploading the file
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": S3_BUCKET, "Key": s3_key, "ContentType": file_type},
            ExpiresIn=EXPIRATION,
        )

        # Log job information
        logger.info(
            f"Created job with ID: {job_id}, workflow: {workflow_name}, schema: {schema_name}, S3 key: {s3_key}"
        )

        # Prepare response
        response_body = {
            "jobId": job_id,
            "bucket": S3_BUCKET,  # Return the actual bucket name
            "key": s3_key,  # Return the actual S3 key
            "uploadUrl": presigned_url,
            "expiresIn": EXPIRATION,
        }

        # Include entity_filenames in response if provided
        if entity_filenames:
            response_body["entityFilenames"] = entity_filenames

        # Return the pre-signed URL, bucket, key, and job ID
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(response_body),
        }
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in request body")
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid JSON in request body"}),
        }
    except Exception as e:
        logger.exception(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
