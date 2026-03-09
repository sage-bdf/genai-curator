# This deliverable is considered developed content as defined in contract between BDF parties.


"""Lambda function that chunks document content by page with a character limit.

This module processes the output from Bedrock Data Automation (BDA), extracts the markdown content
from each page, and creates chunks of pages that stay under a specified character limit.
It writes each chunk to S3 and returns the list of chunks for distributed processing.
"""

import json
import os
from typing import Any, Dict, List, Set

import boto3
from aws_lambda_powertools import Logger

# Configure logging with Lambda Powertools
logger = Logger(service="chunk-task")

CHAR_LIMIT = os.environ.get("CHAR_LIMIT", 20_000)
FILENAME_LIMIT = os.environ.get("FILENAME_LIMIT", 150)
FIELD_LIMIT = os.environ.get("FIELD_LIMIT", 20)


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


def parse_s3_uri(uri: str) -> tuple[str, str]:
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


def extract_job_metadata(event: Dict[str, Any]) -> tuple[str, str, str]:
    """Extract job metadata from the event.

    Args:
        event: Event containing document details

    Returns:
        Tuple of (doc_id, workflow_name, standard_output_path)
    """
    # Extract parameters from the event
    bucket = event.get("bucket")
    job_metadata_uri = event.get("jobMetadataUri")

    if not bucket or not job_metadata_uri:
        raise ValueError("Missing bucket or jobMetadataUri in input")

    # Parse the job metadata URI to get the key
    _, metadata_key = parse_s3_uri(job_metadata_uri)

    # Read the job metadata file
    job_metadata_content = read_file_from_s3(bucket, metadata_key)
    job_metadata = json.loads(job_metadata_content)

    # Extract the document ID from the metadata key
    # Expected format: extract_metadata/nf/jobs/20250609150551-c3b9b72c/input.pdf_bda/job_metadata.json
    parts = metadata_key.split("/")
    if len(parts) < 5:
        raise ValueError(f"Invalid metadata key format: {metadata_key}")

    # The document ID is the directory name after "jobs"
    jobs_index = parts.index("jobs") if "jobs" in parts else -1
    if jobs_index == -1 or jobs_index + 1 >= len(parts):
        raise ValueError(f"Could not find document ID in metadata key: {metadata_key}")

    doc_id = parts[jobs_index + 1]

    # Extract the workflow name from the metadata key
    workflow_name = parts[0]

    # Get the standard output path from the job metadata
    output_metadata = job_metadata.get("output_metadata", [])
    if not output_metadata or len(output_metadata) == 0:
        raise ValueError("No output metadata found in job metadata")

    segment_metadata = output_metadata[0].get("segment_metadata", [])
    if not segment_metadata or len(segment_metadata) == 0:
        raise ValueError("No segment metadata found in output metadata")

    standard_output_path = segment_metadata[0].get("standard_output_path")
    if not standard_output_path:
        raise ValueError("No standard output path found in segment metadata")

    return doc_id, workflow_name, standard_output_path


def extract_schema_name(schema_key: str) -> str:
    """Extract schema name from schema key.

    Args:
        schema_key: S3 key for the schema file

    Returns:
        Schema name
    """
    # Expected schema key format: {workflow_name}/{schema_name}/schema.json
    parts = schema_key.split("/")
    if len(parts) < 3:
        raise ValueError(f"Invalid schema key format: {schema_key}")

    schema_name = parts[1]

    return schema_name


def read_schema(bucket: str, schema_key: str) -> Dict[str, Any]:
    """Read the schema from S3.

    Args:
        bucket: S3 bucket name
        schema_key: S3 key for the schema file

    Returns:
        Schema as a dictionary
    """
    try:
        schema_content = read_file_from_s3(bucket, schema_key)
        return json.loads(schema_content)
    except Exception as e:
        logger.warning(f"Error reading schema from {schema_key}: {str(e)}")
        return {"fields": []}


def chunk_metadata_fields(schema: Dict[str, Any]) -> List[List[str]]:
    """Chunk metadata fields from the schema, ensuring Filename field is in every chunk.

    Args:
        schema: Schema dictionary containing field information

    Returns:
        List of field name chunks, each containing at most FIELD_LIMIT fields
    """
    if not isinstance(schema, dict) or "fields" not in schema or not schema["fields"]:
        logger.warning("No valid schema fields found, cannot chunk fields")
        return [[]]

    # Extract field names from schema
    field_names = [field["name"] for field in schema["fields"]]

    # Find the Filename field (case-insensitive)
    filename_field = next(
        (name for name in field_names if name.lower() == "name"), None
    )

    if not filename_field:
        logger.warning(
            "No 'name' field found in schema, using first field as primary key"
        )
        filename_field = field_names[0] if field_names else None

    # If we have fewer fields than the limit, return a single chunk
    if len(field_names) <= FIELD_LIMIT:
        logger.info(
            f"Schema has {len(field_names)} fields, which is under the limit of {FIELD_LIMIT}. No field chunking needed."
        )
        return [field_names]

    # Remove the filename field from the list to chunk
    if filename_field in field_names:
        field_names.remove(filename_field)

    # Chunk the remaining fields
    field_chunks = []
    for i in range(0, len(field_names), FIELD_LIMIT):
        # Create a chunk with the filename field first, followed by up to FIELD_LIMIT other fields
        chunk = [filename_field] if filename_field else []
        chunk.extend(field_names[i : i + FIELD_LIMIT])
        field_chunks.append(chunk)

    logger.info(
        f"Created {len(field_chunks)} field chunks from {len(field_names) + (1 if filename_field else 0)} fields"
    )
    return field_chunks


def is_horizontal_line(line: str) -> bool:
    """
    Determine if a line is a horizontal separator/border line.

    Args:
        line: The line to check

    Returns:
        True if the line is a horizontal separator, False otherwise
    """
    if not line or len(line) < 3:
        return False

    # Common horizontal line characters
    horizontal_chars = set("-=_*~#")

    # Check if the line consists primarily of a single repeated character
    char_counts = {}
    for char in line:
        if char in horizontal_chars:
            char_counts[char] = char_counts.get(char, 0) + 1

    # If any character appears at least 3 times and makes up more than 70% of the line
    for char, count in char_counts.items():
        if count >= 3 and count / len(line) > 0.7:
            return True

    # Check for common horizontal line patterns
    patterns = [
        "---",
        "===",
        "___",
        "***",
        "~~~",
        "###",  # Simple repeats
        "-+-",
        "-=-",
        "-*-",
        "=*=",  # Alternating patterns
        "-----",
        "=====",
        "_____",
        "*****",  # Longer repeats
    ]

    # Check if any pattern is a significant part of the line (more than 50%)
    # This ensures we're not just matching a small part of a longer line
    for pattern in patterns:
        # If the pattern appears in the line
        if pattern in line:
            # Calculate what percentage of the line is made up by this pattern
            pattern_percentage = len(pattern) / len(line)

            # If the pattern makes up more than 50% of the line, it's likely a horizontal line
            if pattern_percentage > 0.5:
                return True

    return False


def is_primarily_punctuation(line: str) -> bool:
    """
    Determine if a line consists primarily of punctuation or formatting characters.

    Args:
        line: The line to check

    Returns:
        True if the line is primarily punctuation, False otherwise
    """
    if not line:
        return False

    # Count punctuation characters
    punctuation_chars = set(".,;:!?-_=+*/\\|[](){}<>~`'\"\t")
    punctuation_count = sum(1 for c in line if c in punctuation_chars)

    # If more than 30% of the line is punctuation, consider it primarily punctuation
    return (punctuation_count / len(line)) > 0.3


def deduplicate_lines(text: str, min_length: int = 50) -> str:
    """
    Deduplicate lines in a text that are longer than min_length,
    while preserving table structures, horizontal lines, and other important formatting.

    Args:
        text: Input text to deduplicate
        min_length: Minimum line length to consider for deduplication

    Returns:
        Deduplicated text
    """
    # Set to track seen lines
    seen_lines: Set[str] = set()

    # Split the text into lines
    lines = text.splitlines(True)  # Keep the newline characters

    # Process each line
    result = []
    for line in lines:
        # Strip whitespace for comparison but keep original line for writing
        line_stripped = line.strip()

        # Always keep lines in these cases:
        # 1. Line is shorter than min_length
        # 2. Line is a horizontal separator/border
        # 3. Line is likely part of a table structure
        # 4. Line consists primarily of punctuation/formatting characters
        if (
            len(line_stripped) < min_length
            or is_horizontal_line(line_stripped)
            or is_primarily_punctuation(line_stripped)
        ):
            result.append(line)
            continue

        # Check if we've seen this line before
        if line_stripped in seen_lines:
            continue

        # First time seeing this line
        seen_lines.add(line_stripped)
        result.append(line)

    # Join the lines back into a single string
    return "".join(result)


def chunk_document_by_page(
    standard_output_path: str, character_limit: int, entity_filenames: List[str] = None
) -> List[Dict[str, Any]]:
    """Chunk document content by page with a character limit.

    Args:
        standard_output_path: S3 URI to the standard output file
        character_limit: Maximum number of characters per chunk
        entity_filenames: Optional list of entity filenames to distribute across chunks

    Returns:
        List of dictionaries containing chunk information
    """
    # Parse the standard output path to get bucket and key
    output_bucket, output_key = parse_s3_uri(standard_output_path)

    # Read the standard output file
    standard_output_content = read_file_from_s3(output_bucket, output_key)
    standard_output = json.loads(standard_output_content)

    # Extract the pages from the standard output
    pages = standard_output.get("pages", [])
    if not pages:
        raise ValueError("No pages found in standard output")

    # Extract and deduplicate markdown content from each page
    page_contents = []
    for page in pages:
        representation = page.get("representation", {})
        markdown = representation.get("markdown", "")
        if markdown:
            # Deduplicate the content to remove repeated lines
            deduplicated_markdown = deduplicate_lines(markdown)
            page_contents.append(deduplicated_markdown)
        else:
            page_contents.append("")  # Empty string for pages without markdown

    # Create chunks of pages that stay under the character limit
    chunks = []
    current_chunk = []
    current_chunk_size = 0
    current_chunk_pages = []

    for i, content in enumerate(page_contents):
        page_size = len(content)

        # If adding this page would exceed the limit, start a new chunk
        # But only if we already have at least one page in the current chunk
        if current_chunk_size + page_size > character_limit and current_chunk:
            # Save the current chunk
            chunks.append(
                {
                    "pages": current_chunk_pages.copy(),
                    "content": "\n\n".join(current_chunk),
                    "size": current_chunk_size,
                }
            )

            # Start a new chunk with this page
            current_chunk = [content]
            current_chunk_size = page_size
            current_chunk_pages = [i + 1]  # 1-based page numbers
        else:
            # Add this page to the current chunk
            current_chunk.append(content)
            current_chunk_size += page_size
            current_chunk_pages.append(i + 1)  # 1-based page numbers

    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(
            {
                "pages": current_chunk_pages.copy(),
                "content": "\n\n".join(current_chunk),
                "size": current_chunk_size,
            }
        )

    # If entity filenames are provided, we need to create a cross-product of page chunks and filename chunks
    # ensuring no chunk has more than 50 filenames
    if entity_filenames and isinstance(entity_filenames, list):
        # Sort the filenames first to ensure related filenames stay together
        sorted_filenames = sorted(entity_filenames)
        logger.info(f"Sorted {len(sorted_filenames)} filenames for chunking")

        # Determine how many filename chunks we need
        num_filename_chunks = (
            len(sorted_filenames) + FILENAME_LIMIT - 1
        ) // FILENAME_LIMIT

        # Split the sorted filenames into chunks
        filename_chunks = []
        for i in range(num_filename_chunks):
            start_idx = i * FILENAME_LIMIT
            end_idx = min((i + 1) * FILENAME_LIMIT, len(sorted_filenames))
            filename_chunks.append(sorted_filenames[start_idx:end_idx])

        # Create a cross-product of page chunks and filename chunks
        original_chunks = chunks.copy()
        chunks = []

        for page_chunk in original_chunks:
            for filename_chunk in filename_chunks:
                # Create a new chunk with the same page content but different filenames
                new_chunk = page_chunk.copy()
                new_chunk["filename_chunk"] = filename_chunk
                chunks.append(new_chunk)

        logger.info(
            f"Created cross-product of {len(original_chunks)} page chunks and {len(filename_chunks)} filename chunks, resulting in {len(chunks)} total chunks"
        )

    logger.info(f"Created {len(chunks)} chunks from {len(pages)} pages")
    return chunks


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Chunk document content by page with a character limit.

    This function processes the output from Bedrock Data Automation (BDA),
    extracts the markdown content from each page, and creates chunks of pages
    that stay under a specified character limit. It writes each chunk to S3
    and returns the list of chunks for distributed processing.

    Args:
        event: Event containing document details
        context: Lambda context object

    Returns:
        JSON object containing the list of chunks for distributed processing
    """
    logger.info(f"Received event: {event}")

    try:
        # Extract parameters from the event
        bucket = event.get("bucket")
        job_metadata_uri = event.get("jobMetadataUri")
        schema_key = event.get("schemaKey")
        character_limit = event.get("characterLimit", CHAR_LIMIT)
        entity_filenames = event.get("entityFilenames", [])
        output_prefix = event.get("outputPrefix")

        if not bucket or not job_metadata_uri or not schema_key:
            raise ValueError(
                "Missing required parameters: bucket, jobMetadataUri, schemaKey"
            )

        # Extract job metadata
        doc_id, workflow_name, standard_output_path = extract_job_metadata(event)

        # Extract schema name
        schema_name = extract_schema_name(schema_key)

        # Read the schema to get metadata fields
        schema = read_schema(bucket, schema_key)

        # Chunk metadata fields if there are more than FIELD_LIMIT fields
        field_chunks = chunk_metadata_fields(schema)
        logger.info(f"Created {len(field_chunks)} field chunks")

        # Chunk the document by page and distribute entity filenames if provided
        chunks_data = chunk_document_by_page(
            standard_output_path, character_limit, entity_filenames
        )

        # Write each chunk to S3 and prepare the chunk list for the distributed map
        chunks = []

        # Create a cross-product of page chunks, filename chunks, and field chunks
        chunk_counter = 0

        # Use output_prefix if provided, otherwise construct from workflow/schema/doc_id
        chunk_prefix = (
            output_prefix
            if output_prefix
            else f"{workflow_name}/{schema_name}/jobs/{doc_id}"
        )

        for i, chunk in enumerate(chunks_data):
            # Create a unique chunk ID base
            chunk_id_base = f"chunk_{i+1:03d}"

            # Write the chunk content to S3 (only once per content chunk)
            chunk_key = f"{chunk_prefix}/chunks/{chunk_id_base}.md"
            upload_data_to_s3(chunk["content"], bucket, chunk_key, "text/markdown")

            # For each field chunk, create a separate processing chunk
            for j, fields in enumerate(field_chunks):
                chunk_counter += 1
                chunk_id = f"{chunk_id_base}_fields_{j+1:03d}"

                # Add the chunk to the list
                chunk_data = {
                    "bucket": bucket,
                    "schemaKey": schema_key,
                    "markdownKey": chunk_key,
                    "chunkId": chunk_id,
                    "docId": doc_id,
                    "workflow": workflow_name,
                    "pages": chunk["pages"],
                    "size": chunk["size"],
                    "fields": fields,
                    "fieldChunkId": j + 1,
                    "totalFieldChunks": len(field_chunks),
                    "outputPrefix": chunk_prefix,
                }

                # Add entity filenames for this chunk if available
                if "filename_chunk" in chunk:
                    chunk_data["entityFilenames"] = chunk["filename_chunk"]

                chunks.append(chunk_data)

        # Prepare the response
        response = {
            "docId": doc_id,
            "workflow": workflow_name,
            "schemaName": schema_name,
            "bucket": bucket,
            "chunks": chunks,
            "totalChunks": len(chunks),
            "totalFieldChunks": len(field_chunks),
            "outputPrefix": chunk_prefix,
        }

        logger.info(
            f"Successfully created {len(chunks)} chunks (including field chunking)"
        )
        return response

    except Exception as e:
        logger.exception(f"Error chunking document: {str(e)}")
        # Raise the exception for Step Functions to catch
        raise
