# This deliverable is considered developed content as defined in contract between BDF parties.


"""Lambda function that uses MetadataCorrectionPipeline to fix metadata values."""

import asyncio
import json
import os
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

import boto3  # type: ignore
import pandas as pd
from aws_lambda_powertools import Logger  # type: ignore
from pydantic import BaseModel, validator

from fix_values.pipeline import (
    MetadataCorrectionConfig,  # type: ignore
    MetadataCorrectionPipeline,
    PipelineSettings,
)

# Configure logging with Lambda Powertools
logger = Logger(service="fix_metadata")

# Environment variables
BUCKET_NAME = os.environ.get("S3_BUCKET", "genai-curator-data")


class LambdaConfig(BaseModel):
    """Configuration for lambda function."""

    schema_path: Path
    output_dir: Path

    @validator("schema_path", "output_dir", pre=True)
    def ensure_path(cls, v: Optional[Path]) -> Path:
        """Ensure value is a Path object."""
        if v is None:
            raise ValueError("Path cannot be None")
        if not isinstance(v, Path):
            return Path(str(v))
        return v


def read_csv_from_s3(bucket: str, key: str) -> pd.DataFrame:
    """Read a CSV file from S3 into a pandas DataFrame."""
    s3_client = boto3.client("s3")
    logger.info(f"Reading CSV from s3://{bucket}/{key}")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    csv_content = response["Body"].read().decode("utf-8")
    return pd.read_csv(StringIO(csv_content), dtype=str)


def write_csv_to_s3(bucket: str, key: str, df: pd.DataFrame) -> str:
    """Write a pandas DataFrame to S3 as a CSV file."""
    s3_client = boto3.client("s3")
    logger.info(f"Writing CSV to s3://{bucket}/{key}")
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    s3_client.put_object(
        Bucket=bucket, Key=key, Body=csv_buffer.getvalue(), ContentType="text/csv"
    )
    return f"s3://{bucket}/{key}"


def write_json_to_s3(bucket: str, key: str, data: Dict[str, Any]) -> str:
    """Write JSON data to S3."""
    s3_client = boto3.client("s3")
    logger.info(f"Writing JSON to s3://{bucket}/{key}")
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2),
        ContentType="application/json",
    )
    return f"s3://{bucket}/{key}"


def parse_s3_uri(uri: str) -> Tuple[str, str]:
    """Parse an S3 URI into bucket and key.

    Args:
        uri: S3 URI in the format s3://bucket/key

    Returns:
        Tuple of (bucket, key)
    """
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")

    # Remove the s3:// prefix
    path = uri[5:]

    # Split into bucket and key
    parts = path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid S3 URI format: {uri}")

    bucket = parts[0]
    key = parts[1]

    return bucket, key


def extract_workflow_and_schema_name(schema_key: str) -> Tuple[str, str]:
    """Extract workflow name and schema name from schema key.

    Args:
        schema_key: S3 key for the schema file

    Returns:
        Tuple of (workflow_name, schema_name)
    """
    # Expected schema key format: {workflow_name}/{schema_name}/schema.json
    parts = schema_key.split("/")
    if len(parts) < 3:
        raise ValueError(f"Invalid schema key format: {schema_key}")

    workflow_name = parts[0]
    schema_name = parts[1]

    return workflow_name, schema_name


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Process metadata using MetadataCorrectionPipeline.

    Args:
        event: Dictionary containing input parameters
            - sourceTablePath: S3 path to the input CSV file
            - outputPrefix: S3 prefix for output corrected CSV
            - schemaKey: S3 key for schema file
        context: Lambda context

    Returns:
        dict: Dictionary containing information about the corrections applied
    """
    logger.info(f"Received event: {event}")

    try:
        # Handle both direct invocation and API Gateway integration
        if "body" in event:
            body = json.loads(event["body"])
        else:
            body = event

        # Extract input parameters
        source_table_path = body.get("sourceTablePath")
        source_table_path = body.get("sourceTablePath")
        output_prefix = body.get("outputPrefix")
        schema_key = body.get("schemaKey")

        if not all([source_table_path, output_prefix, schema_key]):
            raise ValueError(
                "Missing required parameters: sourceTablePath, outputPrefix, or schemaKey"
            )

        # Cast parameters to string since we've validated they exist
        source_table_path = cast(str, source_table_path)
        output_prefix = cast(str, output_prefix)
        schema_key = cast(str, schema_key)

        # Extract workflow and schema names
        workflow_name, schema_name = extract_workflow_and_schema_name(schema_key)

        # Parse paths
        table_bucket, table_key = parse_s3_uri(source_table_path)
        schema_path = f"s3://{BUCKET_NAME}/{schema_key}"

        logger.info(f"Schema Path: {schema_path}")
        # logger.info(f"Ontology Path: {ontology_path}")

        schema_bucket, schema_key = parse_s3_uri(schema_path)
        # ontology_bucket, ontology_key = parse_s3_uri(ontology_path)

        # Download schema and ontology files to /tmp
        s3_client = boto3.client("s3")
        tmp_schema_path = Path("/tmp/schema.json")
        # tmp_ontology_path = Path("/tmp/ontology.json")
        s3_client.download_file(schema_bucket, schema_key, str(tmp_schema_path))
        # s3_client.download_file(ontology_bucket, ontology_key, str(tmp_ontology_path))

        # Create config
        lambda_config = LambdaConfig(
            schema_path=tmp_schema_path, output_dir=Path("/tmp")
        )

        # Create pipeline config
        pipeline_config = MetadataCorrectionConfig(
            pipeline=PipelineSettings(
                schema_path=lambda_config.schema_path,
                output_dir=lambda_config.output_dir,
            )
        )

        # Read input CSV
        df = read_csv_from_s3(table_bucket, table_key)

        # Initialize pipeline
        pipeline = MetadataCorrectionPipeline(pipeline_config)

        # Process metadata
        loop = asyncio.get_event_loop()
        state = loop.run_until_complete(pipeline.process_metadata(df))

        # Write corrected CSV to S3
        output_key = f"{workflow_name}/{schema_name}/jobs/{output_prefix}/corrected.csv"
        corrected_csv_s3_uri = write_csv_to_s3(BUCKET_NAME, output_key, state.metadata)

        # Write correction history to S3
        corrections_data = {
            "correction_history": [
                {
                    "id": str(attempt.id),
                    "method": attempt.method,
                    "row_idx": attempt.row_idx,
                    "column": attempt.column,
                    "proposed_value": attempt.proposed_value,
                    "confidence": attempt.confidence,
                    "timestamp": attempt.timestamp.isoformat(),
                    "metadata": attempt.metadata,
                }
                for attempt in state.correction_history
            ],
            "errors": [
                {
                    "id": str(error.id),
                    "row_idx": error.row_idx,
                    "column": error.column,
                    "value": error.value,
                    "error_type": error.error_type,
                    "message": error.message,
                    "context": error.context,
                }
                for error in state.errors
            ],
        }
        corrections_key = (
            f"{workflow_name}/{schema_name}/jobs/{output_prefix}/corrections.json"
        )
        corrections_s3_uri = write_json_to_s3(
            BUCKET_NAME, corrections_key, corrections_data
        )

        # Return results
        response = {
            "correctedCsvS3Uri": corrected_csv_s3_uri,
            "correctionsS3Uri": corrections_s3_uri,
            "originalCsvS3Uri": source_table_path,
            "stats": state.stats,
        }

        logger.info(f"Successfully processed metadata and saved results to S3")
        return response

    except Exception as e:
        logger.exception(f"Error processing metadata: {str(e)}")
        # Raise the exception for Step Functions to catch
        raise
