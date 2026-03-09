# This deliverable is considered developed content as defined in contract between BDF parties.


"""Lambda function that applies column operations to create a translated table.

This module consolidates all column translation operations, applies SQL-like operations
to transform source columns into target columns according to the specified mappings,
and produces a final translated table that matches the target schema. It handles various
transformation types including direct mappings, concatenations, and default values.
"""

import datetime
import io
import json
import logging
import os
import re
from typing import Any, List, Optional

import boto3
import pandas as pd
from aws_lambda_powertools import Logger

# Configure logging with Lambda Powertools
logger = Logger(service="consolidate_cols")

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
root_logger = logging.getLogger()
root_logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Environment variables
S3_BUCKET = os.environ.get(
    "S3_BUCKET", "genaicuratorstoragestack-genaicuratorbuckete28236d-vgeq7m7hd70w"
)
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "amazon.nova-pro-v1:0")
SEMANTIC_MATCH_ENABLED = (
    os.environ.get("SEMANTIC_MATCH_ENABLED", "true").lower() == "true"
)

# Cache for semantic matching results to avoid duplicate Bedrock calls
SEMANTIC_MATCH_CACHE = {}

# Counter for Bedrock calls and cache hits
BEDROCK_CALL_COUNT = 0
CACHE_HIT_COUNT = 0


def log_semantic_mapping(
    original_value: str,
    mapped_value: str,
    column_name: str = "",
    is_cached: bool = False,
) -> None:
    """Log semantic mapping for debugging purposes."""
    # Simple logging function
    col_info = f" for column '{column_name}'" if column_name else ""
    cache_info = " (cached)" if is_cached else ""
    logger.info(
        f"SEMANTIC_MAPPING{col_info}{cache_info}: '{original_value}' -> '{mapped_value}'"
    )


def process_column_with_semantic_matching(
    source_values: pd.Series, valid_values: List[str], column_name: str
) -> List[str]:
    """Process a column with semantic matching, using caching for efficiency."""
    # Main function for semantic matching with caching
    global BEDROCK_CALL_COUNT, CACHE_HIT_COUNT

    # Get unique values to reduce Bedrock calls
    unique_values = source_values.dropna().unique()
    logger.info(
        f"Processing {len(source_values)} values ({len(unique_values)} unique) for column '{column_name}'"
    )

    # Create a mapping dictionary for unique values
    value_mapping = {}

    # Process each unique value
    for unique_val in unique_values:
        if pd.isna(unique_val) or unique_val == "":
            continue

        val_str = str(unique_val).strip()
        if not val_str:
            continue

        # First check for exact match
        exact_match = None
        for valid_val in valid_values:
            if str(valid_val).lower() == val_str.lower():
                exact_match = valid_val
                break

        if exact_match:
            value_mapping[val_str] = exact_match
            log_semantic_mapping(val_str, exact_match, column_name)
            continue

        # Check cache
        cache_key = f"{val_str}::{column_name}"
        if cache_key in SEMANTIC_MATCH_CACHE:
            cached_result = SEMANTIC_MATCH_CACHE[cache_key]
            value_mapping[val_str] = cached_result
            CACHE_HIT_COUNT += 1
            log_semantic_mapping(val_str, cached_result, column_name, is_cached=True)
            continue

        # Use Bedrock for semantic matching
        if SEMANTIC_MATCH_ENABLED:
            try:
                bedrock_match = semantic_match_with_bedrock(
                    val_str, valid_values, column_name
                )
                if bedrock_match:
                    value_mapping[val_str] = bedrock_match
                    BEDROCK_CALL_COUNT += 1
                    log_semantic_mapping(val_str, bedrock_match, column_name)
                    continue
                else:
                    # Leave as null if Bedrock couldn't find a match
                    value_mapping[val_str] = None
                    logger.info(
                        f"No semantic match found for '{val_str}', leaving as null"
                    )
                    continue
            except Exception as e:
                logger.error(f"Error using Bedrock for '{val_str}': {e}")
                # Leave as null on error
                value_mapping[val_str] = None
                continue

        # If semantic matching is disabled, leave as null
        value_mapping[val_str] = None
        logger.info(
            f"Semantic matching disabled or failed for '{val_str}', leaving as null"
        )

    # Apply mapping to all values
    result = []
    for val in source_values:
        if pd.isna(val) or val == "":
            result.append("")
        else:
            val_str = str(val).strip()
            # Use None if no mapping was found
            result.append(value_mapping.get(val_str, None))

    logger.info(
        f"Completed semantic mapping for column '{column_name}' - Bedrock calls: {BEDROCK_CALL_COUNT}, Cache hits: {CACHE_HIT_COUNT}"
    )
    return result


def load_source_table(bucket: str, key: str) -> pd.DataFrame:
    """Load source table from S3.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        DataFrame with source data
    """
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read()

        if not content:
            raise ValueError("Empty source file")

        if key.lower().endswith(".csv"):
            return pd.read_csv(io.BytesIO(content))
        elif key.lower().endswith(".json"):
            return pd.read_json(io.BytesIO(content))
        else:
            # Try CSV first, then JSON
            try:
                return pd.read_csv(io.BytesIO(content))
            except:
                return pd.read_json(io.BytesIO(content))
    except Exception as e:
        logger.error(f"Error loading source table from S3: {str(e)}")
        raise


def load_valid_values_from_s3(s3_reference: str) -> List[str]:
    """Load valid values from S3 reference.

    Args:
        s3_reference: S3 path to valid values (s3://bucket/key)

    Returns:
        List of valid values
    """
    if not s3_reference:
        logger.warning(f"Empty S3 reference")
        return []

    # Clean up the S3 reference if needed
    if "*/" in s3_reference:
        s3_reference = s3_reference.split("*/")[-1].strip()
        logger.info(f"Cleaned up S3 reference: {s3_reference}")

    if not s3_reference.startswith("s3://"):
        logger.warning(f"Invalid S3 reference format: {s3_reference}")
        return []

    try:
        # Parse bucket and key from S3 path
        parts = s3_reference.replace("s3://", "").split("/", 1)
        if len(parts) < 2:
            logger.warning(f"Invalid S3 path format: {s3_reference}")
            return []

        bucket = parts[0]
        key = parts[1]

        logger.info(f"Loading valid values from bucket: {bucket}, key: {key}")

        # Load the valid values from S3
        s3_client = boto3.client("s3")
        try:
            # First try the exact key
            try:
                response = s3_client.get_object(Bucket=bucket, Key=key)
                content = response["Body"].read().decode("utf-8")
                logger.info(f"Successfully loaded content from {s3_reference}")
            except s3_client.exceptions.NoSuchKey:
                # If the key doesn't exist, try to list objects with the key as prefix
                logger.warning(
                    f"Key not found: {key}, trying to list objects with this prefix"
                )
                response = s3_client.list_objects_v2(
                    Bucket=bucket, Prefix=key, MaxKeys=1
                )
                if response.get("Contents"):
                    # Use the first object that matches the prefix
                    actual_key = response["Contents"][0]["Key"]
                    logger.info(f"Found matching key: {actual_key}")
                    response = s3_client.get_object(Bucket=bucket, Key=actual_key)
                    content = response["Body"].read().decode("utf-8")
                    logger.info(
                        f"Successfully loaded content from alternative key: {actual_key}"
                    )
                else:
                    # No fallback, just return empty list
                    logger.error(f"No objects found with prefix: {key}")
                    return []

            # Parse the JSON content
            try:
                valid_values = json.loads(content)
                if isinstance(valid_values, list):
                    logger.info(
                        f"Loaded {len(valid_values)} valid values from {s3_reference}"
                    )
                    # Log a sample of the valid values
                    if valid_values:
                        logger.info(f"Sample valid values: {valid_values[:5]}")
                    return valid_values
                else:
                    logger.error(
                        f"Valid values from {s3_reference} is not a list: {type(valid_values)}"
                    )
                    return []
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON from {s3_reference}: {str(e)}")
                # Try to extract values from the content directly
                if content and len(content) > 2:
                    try:
                        # Try to parse as a list of strings
                        if content.startswith("[") and content.endswith("]"):
                            values = [v.strip("\"' ") for v in content[1:-1].split(",")]
                            logger.info(
                                f"Extracted {len(values)} values directly from content"
                            )
                            return values
                    except Exception as e2:
                        logger.error(f"Error extracting values directly: {str(e2)}")
                return []
        except s3_client.exceptions.NoSuchBucket:
            logger.error(f"S3 bucket not found: {bucket}")
            return []
    except Exception as e:
        logger.error(f"Error loading valid values from S3 {s3_reference}: {str(e)}")
        return []


def normalize_string(s: str) -> str:
    """Normalize a string by removing punctuation and extra whitespace."""
    if not s:
        return ""
    # Convert to string, lowercase, remove punctuation, normalize whitespace
    s = str(s).lower().strip()
    for char in [
        ",",
        ".",
        "-",
        "_",
        "/",
        "\\",
        "(",
        ")",
        "[",
        "]",
        "{",
        "}",
        ":",
        ";",
        '"',
        "'",
    ]:
        s = s.replace(char, " ")
    return " ".join(s.split())


def semantic_match_with_bedrock(
    value: str, valid_values: List[str], column_name: str = ""
) -> str:
    """Find the semantically closest match using Bedrock LLM."""
    if not SEMANTIC_MATCH_ENABLED or not value or not valid_values:
        return ""

    # Check cache
    cache_key = f"{value}::{column_name}"
    if cache_key in SEMANTIC_MATCH_CACHE:
        cached_result = SEMANTIC_MATCH_CACHE[cache_key]
        logger.info(
            f"Using cached semantic match for '{value}': '{cached_result}' (column: {column_name})"
        )
        return cached_result

    # Sample values if list is too large
    sample_values = valid_values
    if len(valid_values) > 50:
        start_values = valid_values[:20]
        mid_idx = len(valid_values) // 2
        mid_values = valid_values[mid_idx - 7 : mid_idx + 8]
        end_values = valid_values[-15:]
        sample_values = start_values + mid_values + end_values

    # Prepare prompts
    system_prompt = """
        You are an expert in semantic matching for biomedical terminology.
        Your task is to find the most semantically similar term to the given input value from the provided list of valid values.
        Consider the specific meanings and contexts of the terms in biomedical science.
        """
    user_prompt = f"""
        Input value: "{value}"

        Valid values: {sample_values}

        Return ONLY the single most semantically similar valid value.
        """

    try:
        # Call Bedrock
        bedrock_runtime = boto3.client("bedrock-runtime")
        response = bedrock_runtime.converse(
            modelId=LLM_MODEL_ID,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"maxTokens": 50, "temperature": 0.1},
        )

        match = response["output"]["message"]["content"][0]["text"].strip()
        logger.info(f"Bedrock returned: '{match}' for input '{value}'")
        log_semantic_mapping(value, match, column_name)

        # Check for exact match
        for val in valid_values:
            if (
                val.lower() == match.lower()
                or match.lower() in val.lower()
                or val.lower() in match.lower()
            ):
                SEMANTIC_MATCH_CACHE[cache_key] = val
                return val

    except Exception as e:
        logger.error(f"Bedrock error: {e}")
        return ""


def extract_s3_reference(sql_operation: str) -> Optional[str]:
    """Extract S3 reference from SQL operation comment.

    Args:
        sql_operation: SQL operation string

    Returns:
        S3 reference or None if not found
    """
    if not sql_operation:
        return None

    # Log the full SQL operation for debugging
    logger.info(f"Extracting S3 reference from SQL operation: '{sql_operation}'")

    # Check if the operation contains a valid values reference
    if "VALID_VALUES_REF" not in sql_operation:
        return None

    # Try to extract the S3 reference using a more specific pattern for the format in the event
    pattern = r"VALID_VALUES_REF:\s*(s3://[^\s\*]+)"
    match = re.search(pattern, sql_operation)
    if match:
        s3_ref = match.group(1)
        logger.info(f"Extracted S3 reference: {s3_ref}")
        return s3_ref

    logger.warning(f"Could not extract S3 reference from: {sql_operation}")
    return None


def apply_sql_operations(
    df: pd.DataFrame, column_operations: list[dict]
) -> pd.DataFrame:
    """Apply SQL operations to create the target columns.

    Args:
        df: Source DataFrame
        column_operations: List of column operations

    Returns:
        DataFrame with target columns
    """
    result_data = {}
    column_order = []

    logger.info(f"Available source columns: {list(df.columns)}")

    for op in column_operations:
        column_name = op["column_name"]
        sql_operation = op["sql_operation"]
        valid_values_count = op.get("valid_values_count", 0)
        column_order.append(column_name)

        # Load valid values if needed
        valid_values = []
        s3_reference = (
            extract_s3_reference(sql_operation) if valid_values_count > 0 else None
        )
        if s3_reference:
            logger.info(
                f"Found valid values reference for {column_name}: {s3_reference}"
            )
            valid_values = load_valid_values_from_s3(s3_reference)
            logger.info(f"Loaded {len(valid_values)} valid values for {column_name}")
            if valid_values:
                logger.info(f"Sample valid values: {valid_values[:5]}")
            elif valid_values_count > 0:
                logger.warning(
                    f"Expected {valid_values_count} valid values but loaded 0"
                )

        # Extract SQL expression without AS clause
        sql_expr = sql_operation
        as_clause_patterns = [
            f" AS `{column_name}`",
            f" as `{column_name}`",
            f" AS {column_name}",
            f" as {column_name}",
        ]
        for pattern in as_clause_patterns:
            if pattern in sql_operation:
                sql_expr = sql_operation.split(pattern)[0].strip()
                break

        logger.info(f"SQL expression for {column_name}: '{sql_expr}'")

        # Extract source column
        source_col = extract_source_column(sql_expr, df)

        try:
            # Handle concatenation expressions
            if source_col == "CONCAT_EXPR" and "||" in sql_expr:
                logger.info(
                    f"Processing concatenation expression for {column_name}: {sql_expr}"
                )
                # Extract all columns from the concatenation
                concat_cols = re.findall(r"`([^`]+)`", sql_expr)
                valid_concat_cols = [col for col in concat_cols if col in df.columns]

                if valid_concat_cols:
                    logger.info(f"Concatenating columns: {valid_concat_cols}")
                    # Combine the columns with underscore
                    concat_values = []
                    for idx in range(len(df)):
                        row_values = []
                        for col in valid_concat_cols:
                            val = df[col].iloc[idx]
                            if pd.notna(val) and str(val).strip():
                                row_values.append(str(val).strip())
                        concat_values.append("_".join(row_values) if row_values else "")
                    result_data[column_name] = concat_values
                else:
                    logger.warning(
                        f"No valid columns found for concatenation: {concat_cols}"
                    )
                    result_data[column_name] = [""] * len(df)
                continue

            # If we have a valid source column, process it
            if source_col and source_col in df.columns:
                logger.info(f"Using source column '{source_col}' for {column_name}")
                source_values = df[source_col].fillna("")

                # Apply mapping if we have valid values, otherwise keep original values
                if valid_values:
                    result_data[column_name] = process_column_with_semantic_matching(
                        source_values, valid_values, column_name
                    )
                else:
                    # Trim if this is a TRIM operation, otherwise keep as is
                    if sql_expr.startswith("TRIM("):
                        result_data[column_name] = (
                            source_values.astype(str).str.strip().tolist()
                        )
                    else:
                        result_data[column_name] = source_values.tolist()
                continue

            # Handle specific SQL expressions
            if sql_expr.startswith("CONCAT("):
                concat_cols = [col.strip("`") for col in sql_expr[7:-1].split(", ")]
                result_data[column_name] = (
                    df[concat_cols].astype(str).apply("".join, axis=1)
                )

            elif sql_expr in ["''", '""']:
                result_data[column_name] = [""] * len(df)

            elif sql_expr == "NULL":
                result_data[column_name] = [None] * len(df)

            elif sql_expr.startswith("SUBSTRING_INDEX("):
                # Extract SUBSTRING_INDEX parameters
                match = re.search(
                    r'SUBSTRING_INDEX$\s*`?([^`,]+)`?,\s*[\'"](.*?)[\'"],\s*(-?\d+)\s*$',
                    sql_expr,
                )
                if match:
                    src_col, delimiter, count = (
                        match.group(1).strip("`"),
                        match.group(2),
                        int(match.group(3)),
                    )
                    if src_col in df.columns:
                        result_data[column_name] = process_substring_index(
                            df[src_col], delimiter, count
                        )
                    else:
                        result_data[column_name] = [""] * len(df)
                else:
                    result_data[column_name] = [""] * len(df)

            elif sql_expr in ["0", "FALSE", "[]", json.dumps({})]:
                if sql_expr == "0":
                    result_data[column_name] = [0] * len(df)
                elif sql_expr == "FALSE":
                    result_data[column_name] = [False] * len(df)
                elif sql_expr == "[]":
                    result_data[column_name] = [[] for _ in range(len(df))]
                elif sql_expr == json.dumps({}):
                    result_data[column_name] = [{} for _ in range(len(df))]

            else:
                # For all other cases (CASE, COALESCE, direct column references)
                # Try to find a suitable column
                col = sql_expr.strip("`")
                potential_cols = [col, col.strip("`"), col.strip('"'), col.strip("'")]
                found_col = next((c for c in potential_cols if c in df.columns), None)

                if found_col:
                    logger.info(f"Found source column '{found_col}' for {column_name}")
                    source_values = df[found_col].fillna("")

                    if valid_values:
                        result_data[column_name] = (
                            process_column_with_semantic_matching(
                                source_values, valid_values, column_name
                            )
                        )
                    else:
                        result_data[column_name] = source_values.tolist()
                else:
                    logger.warning(
                        f"Column not found for {column_name}. Using fallback."
                    )
                    if valid_values:
                        result_data[column_name] = [valid_values[0]] * len(df)
                    else:
                        result_data[column_name] = [None] * len(df)

        except Exception as e:
            logger.error(f"Error processing column {column_name}: {str(e)}")
            # Use fallback values
            if valid_values:
                result_data[column_name] = [valid_values[0]] * len(df)
            else:
                result_data[column_name] = [None] * len(df)

    return pd.DataFrame(result_data, columns=column_order)


def extract_source_column(sql_expr: str, df: pd.DataFrame) -> str:
    """Extract the source column name from a SQL expression."""
    # Check for concatenation expressions first
    if "||" in sql_expr:
        return "CONCAT_EXPR"  # Special marker for concatenation

    # Try to extract column from backticks
    backtick_cols = re.findall(r"`([^`]+)`", sql_expr)
    for col in backtick_cols:
        if col in df.columns:
            return col

    # Extract from common SQL patterns
    patterns = [
        # CAST patterns
        r"CAST\s*\(`?([^`\)]+)`?\)",
        r"CAST\s*\(`([^`]+)`\)",
        # COALESCE patterns
        r"COALESCE$TRIM$`([^`]+)`$",
        r"COALESCE$\s*`?([^`,$]+)`?",
        r"COALESCE$\s*TRIM$\s*`?([^`,$]+)`?$",
        # TRIM patterns
        r"TRIM$`([^`]+)`$",
        r"TRIM$\s*`?([^`,$]+)`?",
        # CASE patterns
        r"WHEN\s+LOWER$TRIM$`([^`]+)`$$",
        r"WHEN\s+.*?`([^`]+)`",
    ]

    for pattern in patterns:
        match = re.search(pattern, sql_expr)
        if match:
            col = match.group(1).strip("`")
            if col in df.columns:
                return col

    # Check if any column name directly exists in the expression
    for col in df.columns:
        if col in sql_expr:
            return col

    # This handles cases where the target column name is used as the source
    if sql_expr.strip("`") in df.columns:
        return sql_expr.strip("`")

    return None


def process_substring_index(series, delimiter: str, count: int):
    """Process a series using SUBSTRING_INDEX logic."""
    result_values = []
    for val in series.fillna(""):
        val_str = str(val).strip()
        if not val_str:
            result_values.append("")
            continue

        parts = val_str.split(delimiter)

        if count == 1 and parts:  # First part
            result_values.append(parts[0])
        elif count == -1 and parts:  # Last part
            result_values.append(parts[-1])
        elif count > 0 and parts:  # First N parts
            result_values.append(
                delimiter.join(parts[:count]) if len(parts) >= count else val_str
            )
        elif count < 0 and parts:  # Last N parts
            result_values.append(
                delimiter.join(parts[count:]) if len(parts) >= abs(count) else val_str
            )
        else:
            result_values.append("")

    return result_values


def save_translated_table(
    df: pd.DataFrame, bucket: str, key: str, file_type: str
) -> str:
    """Save the translated table to S3.

    Args:
        df: DataFrame to save
        bucket: S3 bucket name
        key: S3 object key
        file_type: File type (csv or json)

    Returns:
        S3 path where the table was saved
    """
    s3_client = boto3.client("s3")
    try:
        if file_type == "csv":
            csv_buffer = df.to_csv(index=False).encode("utf-8")
            s3_client.put_object(
                Bucket=bucket, Key=key, Body=csv_buffer, ContentType="text/csv"
            )
        elif file_type == "json":
            json_buffer = df.to_json(orient="records").encode("utf-8")
            s3_client.put_object(
                Bucket=bucket, Key=key, Body=json_buffer, ContentType="application/json"
            )
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        return f"s3://{bucket}/{key}"
    except Exception as e:
        logger.error(f"Error saving translated table to S3: {str(e)}")
        raise


def lambda_handler(event: dict, context: Any) -> dict:
    """Apply all column operations to create the final translated table.

    Args:
        event: Step Function event from distributed map
        context: Lambda context

    Returns:
        Dictionary with translated_table_path, success, and stats
    """
    logger.info(f"Received event: {json.dumps(event)}")

    column_operations = []
    source_table_path = None
    target_schema = None

    if isinstance(event, list):
        map_results = event
    else:
        map_results = [event]

    for result in map_results:
        if isinstance(result, dict):
            if not source_table_path:
                source_table_path = result.get("source_table_path")
            if not target_schema:
                target_schema = result.get("target_schema")

            # Handle chunk results with multiple transformations
            if "transformations" in result:
                for transformation in result["transformations"]:
                    # Check if valid_values_count is provided
                    valid_values_count = transformation.get("valid_values_count", 0)
                    logger.info(
                        f"Column {transformation['target_column']} has {valid_values_count} valid values"
                    )

                    column_operations.append(
                        {
                            "column_name": transformation["target_column"],
                            "sql_operation": transformation["sql_transformation"],
                            "valid_values_count": valid_values_count,
                        }
                    )
            elif "sql_transformation" in result and "target_column" in result:
                valid_values_count = result.get("valid_values_count", 0)
                column_operations.append(
                    {
                        "column_name": result["target_column"],
                        "sql_operation": result["sql_transformation"],
                        "valid_values_count": valid_values_count,
                    }
                )

    # Validate required parameters
    if not column_operations:
        raise ValueError("No column operations found in map results")
    if not source_table_path:
        raise ValueError("Missing required parameter: source_table_path")

    logger.info(f"Processing {len(column_operations)} column operations")

    # Debug: Log all column operations
    for i, op in enumerate(column_operations):
        logger.info(
            f"Operation {i+1}: Column '{op['column_name']}' -> SQL: '{op['sql_operation']}'"
        )

    # Extract bucket and key from S3 path
    if source_table_path.startswith("s3://"):
        parts = source_table_path.replace("s3://", "").split("/", 1)
        source_bucket = parts[0]
        source_key = parts[1]
    else:
        source_bucket = S3_BUCKET
        source_key = source_table_path

    logger.info(f"Source Table Bucket: {source_bucket}, Table Key: {source_key}")

    # Load the source table
    source_df = load_source_table(source_bucket, source_key)
    logger.info(
        f"Loaded source table with {len(source_df)} rows and {len(source_df.columns)} columns"
    )

    # Sort column operations by target schema order
    if target_schema:
        schema_order = {col: i for i, col in enumerate(target_schema)}
        column_operations.sort(key=lambda x: schema_order.get(x["column_name"], 999))

    # Apply the column operations
    translated_df = apply_sql_operations(source_df, column_operations)
    logger.info(
        f"Created translated table with {len(translated_df)} rows and {len(translated_df.columns)} columns"
    )

    # Debug: Log sample of translated data
    if len(translated_df) > 0:
        logger.info(
            f"Sample translated data (first row): {translated_df.iloc[0].to_dict()}"
        )
        logger.info(f"Translated columns: {list(translated_df.columns)}")
    else:
        logger.warning("Translated dataframe is empty!")

    # Save the translated table as CSV
    # filename = os.path.basename(source_key).replace(".csv", "")
    filename = source_key.split("/")[1]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    translated_key = f"transform_metadata/output/{filename}_{timestamp}.csv"
    translated_table_path = save_translated_table(
        translated_df, source_bucket, translated_key, "csv"
    )

    stats = {
        "rows_processed": len(source_df),
        "columns_translated": len(column_operations),
        "source_columns": len(source_df.columns),
        "target_columns": len(translated_df.columns),
    }

    return {
        "translated_table_path": translated_table_path,
        "success": True,
        "stats": stats,
        "data": translated_df.to_json(),
    }
