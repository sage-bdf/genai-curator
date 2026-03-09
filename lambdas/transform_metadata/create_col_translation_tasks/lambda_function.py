# This deliverable is considered developed content as defined in contract between BDF parties.


"""Lambda function that creates translation tasks for each column in the target schema.

This module analyzes the target schema, loads sample rows from the source table,
and creates individual translation tasks for each column in the target schema.
These tasks are stored in S3 and will be processed by the translate_col Lambda
function to generate SQL-like operations for transforming source columns to target columns.
"""

import io
import json
import os
from typing import Any

import boto3
import pandas as pd
from aws_lambda_powertools import Logger

# Configure logging with Lambda Powertools
logger = Logger(service="create_col_translation_tasks")

# Environment variables
S3_BUCKET = os.environ.get("S3_BUCKET", "genai-curator-tables")
SAMPLE_ROWS = int(os.environ.get("SAMPLE_ROWS", "10"))  # Number of rows to sample
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "5"))  # Number of columns per chunk


def load_schema(bucket: str, key: str) -> dict:
    """Load a schema from S3.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        Schema as a dictionary
    """
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read()

        if not content:
            raise ValueError("Empty schema file")

        if key.lower().endswith(".csv"):
            logger.info(f"Parsing {key} as CSV schema")
            df = pd.read_csv(io.BytesIO(content))
            columns = df.columns.tolist()
            schema = {"columns": columns}
            return schema
        elif key.lower().endswith(".tsv"):
            logger.info(f"Parsing {key} as TSV schema")
            df = pd.read_csv(io.BytesIO(content), sep="\t")
            columns = df.columns.tolist()
            schema = {"columns": columns}
            return schema
        else:
            raise
    except Exception as e:
        logger.error(f"Error loading schema from S3: {str(e)}")
        raise


def load_sample_rows(
    bucket: str, key: str, file_type: str, num_rows: int = 10
) -> list[dict]:
    """Load a sample of rows from the source table.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        file_type: File type (csv or json)
        num_rows: Number of rows to sample

    Returns:
        List of dictionaries representing rows
    """
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)

        if file_type == "csv" or file_type == "tsv":
            df = pd.read_csv(response["Body"], nrows=num_rows)
            return df.to_dict(orient="records")
        elif file_type == "json":
            data = json.loads(response["Body"].read().decode("utf-8"))
            if isinstance(data, list):
                return data[:num_rows]
            elif isinstance(data, dict) and "records" in data:
                return data["records"][:num_rows]
            else:
                raise ValueError("Unsupported JSON format")
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    except Exception as e:
        logger.error(f"Error loading sample rows from S3: {str(e)}")
        raise


def create_column_tasks(
    task_id: str, target_schema: dict, target_schema_path: str, source_table_path: str
) -> list[dict]:
    """Create translation tasks for chunks of columns in the target schema.

    Args:
        task_id: Unique identifier for the task
        target_schema: Target schema dictionary
        target_schema_path: Path to target schema
        source_table_path: Path to source table

    Returns:
        List of chunk tasks
    """
    chunk_tasks = []

    # Extract columns from the target schema
    columns = []

    for col_name in target_schema.get("columns", []):
        columns.append({"name": col_name, "type": "string"})

    # Create chunks of columns
    for i in range(0, len(columns), CHUNK_SIZE):
        chunk = columns[i : i + CHUNK_SIZE]
        task_key = f"tasks/{task_id}/chunks/chunk_{i // CHUNK_SIZE}.json"

        # Create the chunk task
        chunk_task = {
            "columns": chunk,
            "task_path": f"s3://{S3_BUCKET}/{task_key}",
            "target_schema_path": target_schema_path,
            "source_table_path": source_table_path,
        }

        # Store the task in S3
        s3_client = boto3.client("s3")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=task_key,
            Body=json.dumps(chunk_task),
            ContentType="application/json",
        )

        # Add to the list of tasks
        chunk_tasks.append(
            {
                "chunk_index": i // CHUNK_SIZE,
                "task_path": f"s3://{S3_BUCKET}/{task_key}",
            }
        )

    return chunk_tasks


def lambda_handler(event: dict, context: Any) -> dict:
    """Analyze the target schema and create translation tasks for each column.

    Args:
        event: Step Function event
        context: Lambda context

    Returns:
        Dictionary with task_id and column_tasks
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # Extract parameters from the event
        task_id = event.get("jobId")
        if not task_id:
            raise ValueError("Missing required parameter: jobId")

        # Get bucket and key from the event
        bucket = event.get("bucket")
        input_key = event.get("key")
        logger.info(f"Bucket: {bucket}, Key: {input_key}")

        file = f"{input_key.split('/')[1]}.csv"
        logger.info(f"File: {file}")

        schema_key = f"transform_metadata/schema/{file}"

        s3_client = boto3.client("s3")
        try:
            s3_client.head_object(Bucket=bucket, Key=schema_key)
        except:
            schema_key = schema_key.replace(".csv", ".tsv")

        logger.info(f"Schema Bucket: {bucket}, Schema Key: {schema_key}")

        # Load the target schema
        target_schema = load_schema(bucket, schema_key)

        source_table_path = (f"s3://{bucket}/{input_key}",)
        target_schema_path = f"s3://{bucket}/{schema_key}"

        # Create chunk tasks
        chunk_tasks = create_column_tasks(
            task_id, target_schema, target_schema_path, source_table_path
        )

        # Create the tasks prefix for S3 listing
        translation_tasks_prefix = f"tasks/{task_id}/chunks/"

        # Return the result
        return {
            "task_id": task_id,
            "chunk_tasks": chunk_tasks,
            "source_table_path": f"s3://{bucket}/{input_key}",
            "target_schema_path": f"s3://{bucket}/{schema_key}",
            "translation_tasks_prefix": translation_tasks_prefix,
        }

    except Exception as e:
        logger.exception(f"Error: {str(e)}")
        raise
