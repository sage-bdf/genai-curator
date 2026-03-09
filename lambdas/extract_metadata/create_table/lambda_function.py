# This deliverable is considered developed content as defined in contract between BDF parties.


"""Lambda function that creates a complete table from Bedrock Data Automation output.

This module processes the output from Bedrock Data Automation (BDA), reads the relevant schema,
and uses Bedrock to generate a complete structured table based on the document content.
It saves the resulting table as a CSV file and generates a summary of the extraction results.
"""

import json
import logging
import os
from typing import Any, Dict, List

import boto3
from aws_lambda_powertools import Logger

# Configure logging with Lambda Powertools
logger = Logger(service="create-table")

# Environment variables
LLM_MODEL_ID = os.environ["LLM_MODEL_ID"]
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", 10_000))


def read_file_from_s3(bucket: str, key: str) -> str:
    """Read a file from S3 directly into memory.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        The file content as a string
    """
    s3_client = boto3.client("s3")
    logger.info(f"Reading file from s3://{bucket}/{key}")
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read().decode("utf-8")


def upload_data_to_s3(data: str, bucket: str, key: str, content_type: str) -> None:
    """Upload data directly to S3.

    Args:
        data: String data to upload
        bucket: S3 bucket name
        key: S3 object key
        content_type: Content type of the data
    """
    s3_client = boto3.client("s3")
    logger.info(f"Uploading data to s3://{bucket}/{key}")
    s3_client.put_object(Body=data, Bucket=bucket, Key=key, ContentType=content_type)


def call_bedrock_and_extract_json(
    system_prompt: str, content_items: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Call Bedrock with the given prompts and extract JSON from the response.

    Args:
        system_prompt: The system prompt to use
        content_items: List of content items for the user message

    Returns:
        Parsed JSON result as a list of dictionaries
    """
    # Create a Bedrock client
    bedrock_runtime = boto3.client(service_name="bedrock-runtime")

    logger.info(f"System prompt: {system_prompt}")

    # Call the LLM using the converse_stream API
    response_stream = bedrock_runtime.converse_stream(
        modelId=LLM_MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[
            {
                "role": "user",
                "content": content_items,
            }
        ],
        inferenceConfig={
            "maxTokens": MAX_TOKENS,
        },
    )

    # Process the streaming response
    content = ""
    for event in response_stream["stream"]:
        # Check for content delta events which contain the actual text
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                content += delta["text"]

    logger.info(f"Response text length: {len(content)}")

    # Extract the JSON from the response
    try:
        # Find the JSON part in the response
        json_start = content.find("[")
        json_end = content.rfind("]") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = content[json_start:json_end]
            result = json.loads(json_str)
        else:
            # Fallback: try to parse the entire content as JSON
            result = json.loads(content)

        return result
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM response as JSON")
        raise


def generate_table_from_document(
    document_content: str, schema: Dict[str, Any], fields: List[str] = None
) -> List[Dict[str, Any]]:
    """Generate a complete table from document content using Bedrock.

    Args:
        document_content: Document content extracted from BDA output
        schema: Schema definition for the table
        fields: Optional list of specific fields to extract (for field chunking)

    Returns:
        List of dictionaries representing table rows
    """
    # If specific fields are provided, filter the schema to only include those fields
    filtered_schema = schema.copy()
    if fields and isinstance(fields, list) and "fields" in schema:
        filtered_schema["fields"] = [
            field_def
            for field_def in schema["fields"]
            if field_def.get("name") in fields
        ]
        logger.info(
            f"Filtered schema to {len(filtered_schema['fields'])} fields out of {len(schema['fields'])}"
        )

    # Prepare the system prompt
    system_prompt = """You are an expert biomedical research document analyzer. Your task is to review the text extracted from a research document, then review a metadata schema describing what records and details we hope to find in the document. Respond with a valid JSON list of dictionaries representing all the records contained in the document that fit that schema. If only a subset of fields can be determined for a particular record, include just the fields you can determine for that record.

    Be thorough and generate a dictionary for every single record in the document that fits the schema."""

    # Prepare the user message content items
    schema_json = f"<schema>{json.dumps(filtered_schema, indent=2)}</schema>"
    doc_content = f"<document_content>{document_content}</document_content>"

    content_items = [{"text": schema_json}, {"text": doc_content}]

    # Call Bedrock and extract JSON
    return call_bedrock_and_extract_json(system_prompt, content_items)


def generate_table_from_entities(
    document_content: str,
    schema: Dict[str, Any],
    entity_filenames: List[str],
    fields: List[str] = None,
) -> List[Dict[str, Any]]:
    """Generate a table with rows for each entity filename.

    Args:
        document_content: Document content extracted from BDA output
        schema: Schema definition for the table
        entity_filenames: List of entity filenames to create rows for
        fields: Optional list of specific fields to extract (for field chunking)

    Returns:
        List of dictionaries representing table rows
    """
    # If specific fields are provided, filter the schema to only include those fields
    filtered_schema = schema.copy()
    if fields and isinstance(fields, list) and "fields" in schema:
        filtered_schema["fields"] = [
            field_def
            for field_def in schema["fields"]
            if field_def.get("name") in fields
        ]
        logger.info(
            f"Filtered schema to {len(filtered_schema['fields'])} fields out of {len(schema['fields'])}"
        )

    # Prepare the system prompt
    system_prompt = """You are a biology PhD and an expert in analyzing biomedical research papers. You will be presented with a metadata schema, a list of filenames representing experiment result files, and a research document. Your task is to produce a valid JSON list of dictionaries representing the metadata for each of the result files. Pay close attention to tables, as they may be dense with metadata, but analyze the whole document carefully as some fields may not be listed explicitly - some may even be derived from the filename itself. Try to fill out as many fields as you can for each experiment file, ideally all of them. If you truly cannot infer a field value for a particular experiment result, omit the key from that particular dictionary. If not a single filename can be confidently linked to experiment results in the document, the list may be empty."""

    # Prepare the user message content items
    schema_json = (
        f"<metadata_schema>{json.dumps(filtered_schema, indent=2)}</metadata_schema>"
    )
    filenames = f"<result_filenames>{json.dumps(entity_filenames)}</result_filenames>"
    doc_content = f"<document_content>{document_content}</document_content>"

    content_items = [{"text": schema_json}, {"text": filenames}, {"text": doc_content}]

    # Call Bedrock and extract JSON
    return call_bedrock_and_extract_json(system_prompt, content_items)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Create table rows from a document chunk.

    This function processes a chunk of document content, reads the relevant schema,
    uses Bedrock to generate structured table rows, saves them to S3, and returns
    the S3 path for consolidation.

    Args:
        event: Event containing document chunk details
        context: Lambda context object

    Returns:
        JSON object containing metadata and the S3 path to the generated rows
    """
    logger.info(f"Received event: {event}")

    try:
        # Extract parameters from the event
        bucket = event.get("bucket")
        schema_key = event.get("schemaKey")
        markdown_key = event.get("markdownKey")
        chunk_id = event.get("chunkId")
        doc_id = event.get("docId")
        workflow = event.get("workflow")
        entity_filenames = event.get("entityFilenames")
        fields = event.get("fields")  # Get the fields for this chunk if provided
        field_chunk_id = event.get("fieldChunkId")  # Get the field chunk ID if provided

        if (
            not bucket
            or not schema_key
            or not markdown_key
            or not chunk_id
            or not doc_id
            or not workflow
        ):
            raise ValueError(
                "Missing required parameters: bucket, schemaKey, markdownKey, chunkId, docId, workflow"
            )

        # Extract schema name from schema key
        schema_key_parts = schema_key.split("/")
        schema_name = schema_key_parts[1] if len(schema_key_parts) > 1 else "unknown"

        # Read the markdown content directly from S3
        document_content = read_file_from_s3(bucket, markdown_key)

        # Read the schema
        schema_content = read_file_from_s3(bucket, schema_key)
        schema = json.loads(schema_content)

        # Log field chunking information if present
        if fields and isinstance(fields, list):
            logger.info(
                f"Processing field chunk {field_chunk_id} with {len(fields)} fields"
            )

            # Check if Filename field is included
            filename_field = next((f for f in fields if f.lower() == "name"), None)
            if filename_field:
                logger.info(
                    f"Filename field '{filename_field}' is included in this chunk"
                )
            else:
                logger.warning("Filename field is not included in this chunk")

        # Generate the table based on the scenario
        if entity_filenames:
            # Scenario 1: Use provided entity filenames
            logger.info(f"Using entity filenames: {entity_filenames}")
            table_rows = generate_table_from_entities(
                document_content, schema, entity_filenames, fields
            )
        else:
            # Scenario 2: Infer entities from document (current approach)
            logger.info(
                "No entity filenames provided, inferring entities from document"
            )
            table_rows = generate_table_from_document(document_content, schema, fields)

        # Save the rows to S3
        rows_key = f"{workflow}/{schema_name}/jobs/{doc_id}/chunks/{chunk_id}_rows.json"
        upload_data_to_s3(json.dumps(table_rows), bucket, rows_key, "application/json")

        # Prepare the response
        response = {
            "docId": doc_id,
            "workflow": workflow,
            "schemaName": schema_name,
            "bucket": bucket,
            "chunkId": chunk_id,
            "rowsKey": rows_key,
            "schemaKey": schema_key,  # Include the schema key in the response
            "totalRows": len(table_rows),
            "status": "completed",
        }

        # Include entity_filenames in response if provided
        if entity_filenames:
            response["entityFilenames"] = entity_filenames

        # Include field information in response if provided
        if fields:
            response["fields"] = fields

        if field_chunk_id:
            response["fieldChunkId"] = field_chunk_id

        logger.info(
            f"Successfully created {len(table_rows)} rows from chunk {chunk_id} and saved to S3"
        )
        return response

    except Exception as e:
        logger.exception(f"Error creating table rows: {str(e)}")
        # Raise the exception for Step Functions to catch
        raise
