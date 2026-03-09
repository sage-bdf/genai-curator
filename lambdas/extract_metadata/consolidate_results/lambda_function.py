# This deliverable is considered developed content as defined in contract between BDF parties.


"""Lambda function that consolidates results from distributed processing into a single CSV file.

This module retrieves all results generated from distributed processing of document chunks,
combines them into a structured dataset, creates a single CSV file with all rows,
and generates a summary of the extraction results.
"""

import csv
import json
import os
import tempfile
from typing import Any, Dict, List, Optional

import boto3
from aws_lambda_powertools import Logger

# Configure logging with Lambda Powertools
logger = Logger(service="consolidate-results")


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


def upload_file_to_s3(
    local_path: str, bucket: str, key: str, content_type: str
) -> None:
    """Upload a file to S3.

    Args:
        local_path: Local file path to upload
        bucket: S3 bucket name
        key: S3 object key
        content_type: Content type of the file
    """
    s3_client = boto3.client("s3")
    logger.info(f"Uploading file from {local_path} to s3://{bucket}/{key}")
    s3_client.upload_file(
        local_path, bucket, key, ExtraArgs={"ContentType": content_type}
    )


def find_entity_filenames(chunks: List[Dict[str, Any]]) -> Optional[List[str]]:
    """Collect all unique entity filenames from all chunks.

    Args:
        chunks: List of chunk items from the event

    Returns:
        List of unique entity filenames if found, None otherwise
    """
    all_filenames = set()

    for chunk in chunks:
        if "entityFilenames" in chunk:
            chunk_filenames = chunk.get("entityFilenames")
            if isinstance(chunk_filenames, list):
                # Add all filenames from this chunk to our set
                all_filenames.update(chunk_filenames)

    if all_filenames:
        unique_filenames = list(all_filenames)
        logger.info(
            f"Found {len(unique_filenames)} unique entity filenames across all chunks"
        )
        return unique_filenames

    return None


def collect_all_fields(chunks: List[Dict[str, Any]]) -> List[str]:
    """Collect all unique field names from all chunks.

    Args:
        chunks: List of chunk items from the event

    Returns:
        List of all unique field names
    """
    all_fields = set()

    for chunk in chunks:
        if "fields" in chunk and isinstance(chunk["fields"], list):
            all_fields.update(chunk["fields"])

    unique_fields = list(all_fields)
    logger.info(f"Found {len(unique_fields)} unique fields across all chunks")
    return unique_fields


def read_schema(bucket: str, schema_key: str) -> Dict[str, Any]:
    """Read the schema from S3.

    Args:
        bucket: S3 bucket name
        schema_key: S3 key for the schema file

    Returns:
        Schema as a dictionary, or empty schema if not found
    """
    try:
        schema_content = read_file_from_s3(bucket, schema_key)
        return json.loads(schema_content)
    except Exception as e:
        logger.warning(f"Error reading schema from {schema_key}: {str(e)}")
        return {"fields": []}


def collect_rows_from_chunks(
    chunks: List[Dict[str, Any]], bucket: str
) -> List[Dict[str, Any]]:
    """Collect all rows from all chunks by reading the S3 JSON files.

    Args:
        chunks: List of chunk items from the event
        bucket: S3 bucket name

    Returns:
        List of all rows collected from chunks
    """
    all_rows = []

    # Group results by chunk ID base (without field chunk suffix)
    # This helps us identify which results are from the same document chunk but different field chunks
    chunk_groups = {}

    for chunk in chunks:
        # Each chunk should have a rows key pointing to an S3 location
        rows_key = chunk.get("rowsKey")
        if not rows_key:
            continue

        # Extract the chunk ID and check if it has field chunking
        chunk_id = chunk.get("chunkId", "")
        if "_fields_" in chunk_id:
            # This is a field-chunked ID, extract the base chunk ID
            base_chunk_id = chunk_id.split("_fields_")[0]
        else:
            # This is a regular chunk ID
            base_chunk_id = chunk_id

        # Add to the appropriate group
        if base_chunk_id not in chunk_groups:
            chunk_groups[base_chunk_id] = []
        chunk_groups[base_chunk_id].append(chunk)

    # Process each chunk group
    for base_chunk_id, group_chunks in chunk_groups.items():
        # For each group, collect and merge rows from all field chunks
        chunk_rows = []

        for chunk in group_chunks:
            rows_key = chunk.get("rowsKey")
            fields = chunk.get("fields", [])

            try:
                # Read the rows from S3
                rows_content = read_file_from_s3(bucket, rows_key)
                rows = json.loads(rows_content)

                if not rows:
                    continue

                # If this is a field chunk, we need to merge rows based on the primary key (name)
                if fields and "fieldChunkId" in chunk:
                    # Find the primary key field (name)
                    primary_key_field = next(
                        (field for field in fields if field.lower() == "name"),
                        fields[0] if fields else None,
                    )

                    if not primary_key_field:
                        # If no primary key field, just add the rows as-is
                        chunk_rows.extend(rows)
                        continue

                    # For each row in this field chunk
                    for row in rows:
                        if not isinstance(row, dict):
                            continue

                        primary_key = row.get(primary_key_field)
                        if not primary_key:
                            # Skip rows without a primary key
                            continue

                        # Check if we already have a row with this primary key
                        existing_row = next(
                            (
                                r
                                for r in chunk_rows
                                if r.get(primary_key_field) == primary_key
                            ),
                            None,
                        )

                        if existing_row:
                            # Merge this row with the existing row
                            # Only copy fields that are in this field chunk
                            for field in fields:
                                if field in row and row[field]:
                                    existing_row[field] = row[field]
                        else:
                            # Add this as a new row
                            chunk_rows.append(row)
                else:
                    # No field chunking, just add the rows as-is
                    chunk_rows.extend(rows)

            except Exception as e:
                logger.warning(f"Error reading rows from {rows_key}: {str(e)}")

        # Add all rows from this chunk group to the overall results
        all_rows.extend(chunk_rows)

    if not all_rows:
        logger.warning(f"No rows found in any of the {len(chunks)} chunks")

    return all_rows


def process_entity_filenames(
    all_rows: List[Dict[str, Any]],
    entity_filenames: Optional[List[str]],
    schema: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Process entity filenames to ensure all are included in the output.

    Args:
        all_rows: List of all rows collected from chunks
        entity_filenames: List of entity filenames to ensure are included
        schema: Schema dictionary containing field information

    Returns:
        List of rows with all entities included
    """
    if (
        not entity_filenames
        or not isinstance(schema, dict)
        or "fields" not in schema
        or not schema["fields"]
    ):
        return all_rows

    logger.info("Processing entity filenames to ensure all are included in the output")

    # Look for "name" field in schema, or fall back to first field if not found
    entity_field = next(
        (
            field["name"]
            for field in schema["fields"]
            if field["name"].lower() == "name"
        ),
        schema["fields"][0]["name"],
    )
    logger.info(f"Using {entity_field} as the entity identifier field")

    # Create a mapping of existing rows by entity name
    existing_entities = {}
    for row in all_rows:
        if isinstance(row, dict):
            entity_id = row.get(entity_field, "")
            if entity_id:
                # Store by both full name and basename (without extension)
                existing_entities[entity_id] = row
                # Also store by basename for matching with cleaned entity names
                basename = entity_id.split(".")[0] if "." in entity_id else entity_id
                existing_entities[basename] = row

    # Ensure all requested entities are included
    final_rows = []
    for entity_name in entity_filenames:
        if not isinstance(entity_name, str):
            logger.warning(f"Skipping non-string entity name: {entity_name}")
            continue

        # Clean up entity name (remove file extension if present)
        clean_entity_name = (
            entity_name.split(".")[0] if "." in entity_name else entity_name
        )

        # Try to match by full name or basename
        if entity_name in existing_entities:
            logger.info(f"Entity {entity_name} found in existing rows")
            final_rows.append(existing_entities[entity_name])
        elif clean_entity_name in existing_entities:
            logger.info(f"Entity {clean_entity_name} found in existing rows")
            final_rows.append(existing_entities[clean_entity_name])
        else:
            logger.info(f"Creating empty row for entity {entity_name}")
            # Create an empty row for this entity
            empty_row = {field["name"]: "" for field in schema["fields"]}
            empty_row[entity_field] = entity_name  # Use full filename
            final_rows.append(empty_row)

    return final_rows


def create_csv_file(
    all_rows: List[Dict[str, Any]],
    bucket: str,
    output_prefix: str,
    schema: Dict[str, Any] = None,
) -> str:
    """Create a CSV file with all rows and upload it to S3.

    Args:
        all_rows: List of all rows to include in the CSV
        bucket: S3 bucket name
        output_prefix: The S3 prefix where output files will be written
        schema: Schema dictionary containing field information

    Returns:
        S3 key of the uploaded CSV file
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Determine field order based on schema if available
        ordered_fields = []
        additional_fields = set()

        # First, get all fields from all rows to ensure we don't miss any
        all_row_fields = set()
        for row in all_rows:
            all_row_fields.update(row.keys())

        # If schema is available, use its field order
        if (
            schema
            and isinstance(schema, dict)
            and "fields" in schema
            and schema["fields"]
        ):
            # Add schema fields in the order they're defined
            for field in schema["fields"]:
                field_name = field["name"]
                if field_name in all_row_fields:
                    ordered_fields.append(field_name)
                    all_row_fields.remove(field_name)

        # Add any remaining fields that weren't in the schema
        additional_fields = sorted(all_row_fields)
        final_fields = ordered_fields + additional_fields

        logger.info(
            f"Using {len(ordered_fields)} fields from schema and {len(additional_fields)} additional fields"
        )

        # Create CSV file
        csv_filename = "final.csv"
        csv_path = os.path.join(temp_dir, csv_filename)

        with open(csv_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=final_fields)
            writer.writeheader()
            for row in all_rows:
                writer.writerow(row)

        # Upload CSV to S3 - place directly in the output prefix
        csv_key = f"{output_prefix}/{csv_filename}"
        upload_file_to_s3(csv_path, bucket, csv_key, "text/csv")

    return csv_key


def create_summary_file(
    doc_id: str,
    workflow_name: str,
    schema_name: str,
    all_rows: List[Dict[str, Any]],
    csv_key: str,
    bucket: str,
    output_prefix: str,
) -> str:
    """Create and upload a summary file to S3.

    Args:
        doc_id: Document ID
        workflow_name: Name of the workflow
        schema_name: Name of the schema
        all_rows: List of all rows in the CSV
        csv_key: S3 key of the CSV file
        bucket: S3 bucket name
        output_prefix: The S3 prefix where output files will be written

    Returns:
        S3 key of the uploaded summary file
    """
    # Create a summary file
    summary = {
        "docId": doc_id,
        "workflow": workflow_name,
        "schemaName": schema_name,
        "totalRows": len(all_rows),
        "csvKey": csv_key,
    }

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as temp_file:
        json.dump(summary, temp_file)
        temp_file.flush()
        summary_path = temp_file.name

    # Upload the summary file to S3
    summary_key = f"{output_prefix}/summary.json"
    upload_file_to_s3(summary_path, bucket, summary_key, "application/json")

    # Clean up the temporary file
    os.unlink(summary_path)

    return summary_key


def prepare_response(
    doc_id: str,
    workflow_name: str,
    schema_name: str,
    bucket: str,
    summary_key: str,
    all_rows: List[Dict[str, Any]],
    csv_key: str,
    entity_filenames: Optional[List[str]],
) -> Dict[str, Any]:
    """Prepare the response object.

    Args:
        doc_id: Document ID
        workflow_name: Name of the workflow
        schema_name: Name of the schema
        bucket: S3 bucket name
        summary_key: S3 key of the summary file
        all_rows: List of all rows in the CSV
        csv_key: S3 key of the CSV file
        entity_filenames: List of entity filenames if provided

    Returns:
        Response dictionary
    """
    response = {
        "docId": doc_id,
        "workflow": workflow_name,
        "schemaName": schema_name,
        "bucket": bucket,
        "summaryKey": summary_key,
        "totalRows": len(all_rows),
        "csvKey": csv_key,
        "status": "completed",
        "outputLocation": f"s3://{bucket}/{csv_key}",
    }

    # Include entity_filenames in response if provided
    if entity_filenames:
        response["entityFilenames"] = entity_filenames

    logger.info(f"Successfully consolidated {len(all_rows)} rows")
    return response


def deduplicate_rows(
    all_rows: List[Dict[str, Any]], schema: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Deduplicate rows based on a key field (typically name).

    If the same entity appears in multiple chunks, this function will merge them,
    keeping the most complete data for each field.

    Args:
        all_rows: List of all rows collected from chunks
        schema: Schema dictionary containing field information

    Returns:
        List of deduplicated rows
    """
    if not all_rows:
        return all_rows

    if not isinstance(schema, dict) or "fields" not in schema or not schema["fields"]:
        logger.warning("No valid schema fields found, cannot deduplicate rows")
        return all_rows

    # Look for "name" field in schema, or fall back to first field if not found
    key_field = next(
        (
            field["name"]
            for field in schema["fields"]
            if field["name"].lower() == "name"
        ),
        schema["fields"][0]["name"],
    )
    logger.info(f"Using {key_field} as the key field for deduplication")

    # Create a dictionary to store the deduplicated rows
    deduplicated = {}

    for row in all_rows:
        if not isinstance(row, dict):
            continue

        key = row.get(key_field)
        if not key:  # Skip rows without a key
            continue

        if key in deduplicated:
            # Merge with existing row, preferring non-empty values
            for field, value in row.items():
                if value and not deduplicated[key].get(field):
                    deduplicated[key][field] = value
        else:
            # New unique row
            deduplicated[key] = row

    logger.info(
        f"Deduplicated {len(all_rows)} rows into {len(deduplicated)} unique rows"
    )
    return list(deduplicated.values())


def enforce_schema_on_rows(
    all_rows: List[Dict[str, Any]], schema: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Enforce the schema on all rows, ensuring all fields from the schema are present.

    Args:
        all_rows: List of all rows collected from chunks
        schema: Schema dictionary containing field information

    Returns:
        List of rows with all schema fields included
    """
    if not isinstance(schema, dict) or "fields" not in schema or not schema["fields"]:
        logger.warning("No valid schema fields found, returning rows as-is")
        return all_rows

    # Get all field names from the schema
    schema_fields = [field["name"] for field in schema["fields"]]
    logger.info(
        f"Enforcing schema with {len(schema_fields)} fields on {len(all_rows)} rows"
    )

    # Ensure all rows have all fields from the schema
    enforced_rows = []
    for row in all_rows:
        if not isinstance(row, dict):
            logger.warning(f"Skipping non-dictionary row: {row}")
            continue

        # Create a new row with all schema fields
        enforced_row = {field: row.get(field, "") for field in schema_fields}

        # Add any additional fields that might be in the row but not in the schema
        for key, value in row.items():
            if key not in enforced_row:
                enforced_row[key] = value

        enforced_rows.append(enforced_row)

    return enforced_rows


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Consolidate results from distributed processing into a single CSV file.

    This function retrieves all results generated from distributed processing of document chunks,
    reads the rows from S3 JSON files, combines them into a structured dataset,
    creates a single CSV file with all rows, and generates a summary of the extraction results.

    Args:
        event: Event containing document details and results from distributed processing
        context: Lambda context object

    Returns:
        JSON object containing the S3 path to the final CSV file, summary statistics,
        and metadata extraction completion status
    """
    logger.info(f"Received event: {event}")

    try:
        # Extract metadata from the event
        bucket = event.get("bucket")
        output_prefix = event.get("output_prefix")
        chunks = event.get("chunks", [])

        if not bucket or not output_prefix:
            raise ValueError("Missing required parameters: bucket, output_prefix")

        if not chunks or not isinstance(chunks, list) or len(chunks) == 0:
            raise ValueError("No chunks found in event or invalid chunks format")

        # Get the first chunk to extract common metadata
        first_chunk = chunks[0]
        doc_id = first_chunk.get("docId")
        workflow_name = first_chunk.get("workflow")
        schema_name = first_chunk.get("schemaName", None)
        schema_key = first_chunk.get("schemaKey")

        if not doc_id or not workflow_name:
            raise ValueError("Missing required metadata in chunks")

        # Find entity filenames if present
        entity_filenames = find_entity_filenames(chunks)

        # Collect all unique fields from all chunks
        all_fields = collect_all_fields(chunks)
        logger.info(f"Collected {len(all_fields)} unique fields across all chunks")

        # Read the schema - prefer using the schema_key if available
        if schema_key:
            logger.info(f"Using schema key from create_table lambda: {schema_key}")
            try:
                schema_content = read_file_from_s3(bucket, schema_key)
                schema = json.loads(schema_content)
            except Exception as e:
                logger.warning(f"Error reading schema from {schema_key}: {str(e)}")
                # Fall back to constructed path
                schema = {"fields": []}
        else:
            # Fall back to empty schema
            logger.info("No schema key provided, using empty schema")
            schema = {"fields": []}

        # Collect rows from chunks - this now handles merging field chunks
        all_rows = collect_rows_from_chunks(chunks, bucket)
        logger.info(
            f"Collected {len(all_rows)} rows from all chunks after merging field chunks"
        )

        # Deduplicate rows that might appear in multiple chunks
        all_rows = deduplicate_rows(all_rows, schema)
        logger.info(f"After deduplication: {len(all_rows)} rows")

        # Enforce schema on all rows to ensure all fields are present
        all_rows = enforce_schema_on_rows(all_rows, schema)

        # Process entity filenames if provided
        if entity_filenames:
            all_rows = process_entity_filenames(all_rows, entity_filenames, schema)
            logger.info(f"After processing entity filenames: {len(all_rows)} rows")

        # Create CSV file
        csv_key = create_csv_file(all_rows, bucket, output_prefix, schema)

        # Create summary file
        summary_key = create_summary_file(
            doc_id, workflow_name, schema_name, all_rows, csv_key, bucket, output_prefix
        )

        # Prepare and return response
        response = prepare_response(
            doc_id,
            workflow_name,
            schema_name,
            bucket,
            summary_key,
            all_rows,
            csv_key,
            entity_filenames,
        )

        # Add field chunking information to the response
        field_chunks_count = max(
            [
                chunk.get("totalFieldChunks", 1)
                for chunk in chunks
                if "totalFieldChunks" in chunk
            ],
            default=1,
        )
        if field_chunks_count > 1:
            response["totalFieldChunks"] = field_chunks_count
            response["totalFields"] = len(all_fields)

        return response

    except Exception as e:
        logger.exception(f"Error consolidating results: {str(e)}")
        # Raise the exception for Step Functions to catch
        raise
