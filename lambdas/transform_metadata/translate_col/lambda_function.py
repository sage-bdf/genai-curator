# This deliverable is considered developed content as defined in contract between BDF parties.


import ast
import io
import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Tuple

import boto3
import pandas as pd
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

# Configure logging
logger = Logger(service="column_translator")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

# Environment variables
S3_BUCKET = os.environ.get("S3_BUCKET", "your-s3-bucket")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "amazon.nova-pro-v1:0")
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "70"))


def load_chunk_task(bucket: str, key: str) -> dict:
    """Load a chunk task from S3.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        Chunk task as a dictionary
    """
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        task_str = response["Body"].read().decode("utf-8")
        return json.loads(task_str)
    except Exception as e:
        logger.error(f"Error loading chunk task from S3: {str(e)}")
        raise


class ColumnTranslator:
    def __init__(self, bedrock_runtime=None):
        """
        Initialize the column translator with Bedrock runtime

        Args:
            bedrock_runtime: Optional pre-configured Bedrock client
        """
        self.bedrock_runtime = bedrock_runtime or boto3.client("bedrock-runtime")
        self.column_operations = {}

    def batch_semantic_column_match(
        self,
        source_columns: List[str],
        target_columns: List[str],
        target_df=None,
        source_df=None,
    ) -> List[Tuple[str, str, float]]:
        """
        Use Bedrock to perform semantic column matching for multiple columns at once

        Args:
            source_columns: List of source column names
            target_columns: List of target columns to match

        Returns:
            List of tuples (target_column, best_match, confidence_score)
        """
        system_prompt = """
        You are an expert data schema mapping specialist in the biomedical research field. Your task is to:
        1. Find the most semantically similar source column for each target column
        2. Provide a confidence score for each match
        3. Explain your reasoning briefly

        Consider:
        - Semantic meaning
        - Word relationships
        - Potential data transformations
        - Column splitting (e.g., full_name can be split into first_name and last_name)

        IMPORTANT: When a target column can be derived from a source column through splitting or transformation,
        consider it a strong match with high confidence (90+). For example, 'last_name' can be derived from 'full_name'
        by splitting, so this should be a high confidence match.
        """

        # Build enhanced column info with descriptions
        target_info = []
        for i, col in enumerate(target_columns):
            desc = ""
            if target_df is not None and f"{col}_description" in target_df.columns:
                desc_values = target_df[f"{col}_description"].dropna().tolist()
                if desc_values:
                    desc = f" (Description: {desc_values[0]})"
            target_info.append(f"{i+1}. {col}{desc}")

        source_info = []
        for col in source_columns:
            desc = ""
            if source_df is not None and f"{col}_description" in source_df.columns:
                desc_values = source_df[f"{col}_description"].dropna().tolist()
                if desc_values:
                    desc = f" (Description: {desc_values[0]})"
            source_info.append(f"{col}{desc}")

        target_list = "\n".join(target_info)
        user_prompt = f"""
        Context:
        - Source Columns: {', '.join(source_info)}
        - Target Columns to Match:
        {target_list}

        For each target column, identify the most semantically similar source column.
        Remember that source columns can be transformed or split to derive target columns.
        For example, 'first_name' and 'last_name' can both be derived from 'full_name' with high confidence.

        Output Format (one per line):
        Target: [target_column] | Match: [source_column] | Confidence: [score]
        """

        try:
            response = self._bedrock_call_with_retry(
                system_prompt, user_prompt, max_tokens=800, temperature=0.3
            )

            content = response["output"]["message"]["content"][0]["text"]
            logger.info(f"AI Batch Response: {content}")

            # Parse batch response
            results = []
            for target_col in target_columns:
                best_match, confidence = self._parse_batch_response(
                    content, source_columns, target_col
                )
                results.append((target_col, best_match, confidence))

            return results

        except Exception as e:
            logger.error(f"Batch Bedrock Error: {e}")

    def _process_column_operations(
        self, transformations_data: List[Dict[str, Any]]
    ) -> None:
        """
        Process column operations to identify columns that need to be split or combined

        Args:
            transformations_data: List of transformation data dictionaries
        """
        # Reset column operations
        self.column_operations = {}

        # Get all target and source columns
        target_to_source = {}
        source_to_targets = {}

        # Build mappings
        for data in transformations_data:
            target_col = data["target_column"]
            source_col = data.get("source_column")
            if source_col:
                target_to_source[target_col] = source_col
                if source_col not in source_to_targets:
                    source_to_targets[source_col] = []
                source_to_targets[source_col].append(target_col)

        # Find columns that need to be split (multiple target columns from same source)
        for source_col, target_cols in source_to_targets.items():
            if len(target_cols) > 1:
                logger.info(f"Potential column split: {source_col} -> {target_cols}")
                self._setup_auto_split(source_col, target_cols)

        # Log all detected operations
        if self.column_operations:
            logger.info(
                f"Detected {len(self.column_operations)} column operations: {list(self.column_operations.keys())}"
            )

    def _setup_auto_split(self, source_col: str, target_cols: List[str]) -> None:
        """Setup automatic splitting based on column names and positions"""
        logger.info(f"Setting up auto split for {source_col} -> {target_cols}")

        # Sort target columns to maintain consistent order
        sorted_cols = sorted(target_cols)

        # Set up split operations for each target column
        for i, col in enumerate(sorted_cols):
            self.column_operations[col] = {
                "operation": "auto_split",
                "source_column": source_col,
                "position": i,
                "total_parts": len(sorted_cols),
            }

    def _generate_split_column_sql(
        self,
        source_column: str,
        target_column: str,
        operation_type: str,
        position: int = 0,
        total_parts: int = 2,
    ) -> str:
        """
        Generate SQL to split a column based on operation type

        Args:
            source_column: Source column name
            target_column: Target column name
            operation_type: Type of operation
            position: Position for splits (0-based)
            total_parts: Total number of parts to split into

        Returns:
            SQL expression for the transformation
        """
        # Use a generic approach for auto_split
        if operation_type == "auto_split":
            # First part (position 0)
            if position == 0:
                sql = f"SUBSTRING_INDEX(`{source_column}`, ' ', 1) AS `{target_column}`"
            # Last part
            elif position == total_parts - 1:
                sql = (
                    f"SUBSTRING_INDEX(`{source_column}`, ' ', -1) AS `{target_column}`"
                )
            # Middle parts
            else:
                # For middle parts, extract the nth word
                # This gets the first n+1 words, then takes the last word of that
                sql = f"SUBSTRING_INDEX(SUBSTRING_INDEX(`{source_column}`, ' ', {position + 1}), ' ', -1) AS `{target_column}`"
        else:
            # Default to direct mapping
            sql = f"`{source_column}` AS `{target_column}`"

        return sql

    def batch_generate_column_transformations(
        self, transformations_data: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Generate SQL transformations for multiple columns using Bedrock

        Args:
            transformations_data: List of dicts with keys: source_column, target_column, valid_values, has_valid_values

        Returns:
            List of SQL transformation expressions
        """
        # Process column operations to identify splits and combines
        self._process_column_operations(transformations_data)
        system_prompt = """
        You are an advanced SQL data transformation expert. Generate precise
        SQL transformations for multiple columns that:
        1. Convert source columns to target column formats
        2. Handle data type conversions
        3. Normalize values
        4. Ensure data integrity
        5. Match values to the closest valid value in the provided list
        """

        transformations_text = []
        for i, data in enumerate(transformations_data):
            # Only show a preview of valid values to avoid token limits
            valid_values = data.get("valid_values", [])
            preview_values = (
                valid_values[:10] if len(valid_values) > 10 else valid_values
            )

            # Store full valid values in S3 if there are many
            s3_reference = ""
            if len(valid_values) > 20 and data.get("has_valid_values", False):
                s3_reference = self._store_valid_values_in_s3(
                    data["target_column"], valid_values
                )

            transformations_text.append(
                f"{i+1}. Source: {data['source_column']} -> Target: {data['target_column']}\n"
                f"   Valid Values Preview: {preview_values}\n"
                f"   Total Valid Values: {len(valid_values)}\n"
                f"   Valid Values S3 Reference: {s3_reference if s3_reference else 'None'}\n"
                f"   Has Values: {data.get('has_valid_values', True)}"
            )

        user_prompt = f"""
        Generate SQL transformation expressions for these columns:

        {chr(10).join(transformations_text)}

        IMPORTANT: When a column has valid values, use CASE statements or other SQL constructs to map input values
        to the EXACT values from the valid_values list. The transformed value must match EXACTLY one of the values
        in the valid_values list, using string similarity to find the closest match when needed.

        CRITICAL FORMATTING RULES:
        1. DO NOT include any 'AS' or column aliasing in your expressions
        2. Return only the transformation logic (e.g., TRIM(`source_column`) or CASE WHEN...)
        3. I will add the proper column aliasing later

        Output Format (one per line):
        {i+1}. [SQL_EXPRESSION]

        Output ONLY the SQL transformation expressions with their numbers.
        """

        try:
            response = self._bedrock_call_with_retry(
                system_prompt, user_prompt, max_tokens=1000, temperature=0.4
            )

            content = response["output"]["message"]["content"][0]["text"]

            # Parse batch SQL response
            sql_expressions = self._parse_batch_sql_response(
                content, transformations_data
            )

            return sql_expressions

        except Exception as e:
            logger.error(f"Batch SQL Generation Error: {e}")
            # Fallback to individual generation
            results = []
            for data in transformations_data:
                sql_expr = self.generate_column_transformation(
                    data["source_column"],
                    data["target_column"],
                    data.get("valid_values", []),
                    data.get("has_valid_values", True),
                )
                results.append(sql_expr)
            return results

    def _parse_batch_response(
        self, content: str, source_columns: List[str], target_column: str
    ) -> Tuple[str, float]:
        """Parse batch AI response for a specific target column."""
        # Split content into lines
        lines = content.split("\n")

        for line in lines:
            if target_column in line and "Match:" in line and "Confidence:" in line:
                try:
                    # Extract match using regex
                    match_pattern = r"Match:\s*([^|]+)\|"
                    match_result = re.search(match_pattern, line)

                    # Extract confidence using regex
                    conf_pattern = r"Confidence:\s*(\d+)"
                    conf_result = re.search(conf_pattern, line)

                    if match_result and conf_result:
                        match_value = match_result.group(1).strip()
                        confidence = float(conf_result.group(1))

                        # Validate the match
                        if self._validate_column_match(match_value, source_columns):
                            logger.info(
                                f"Found match for {target_column}: {match_value} with confidence {confidence}%"
                            )
                            return match_value, confidence
                except Exception as e:
                    logger.warning(f"Error parsing line: {line}, error: {e}")

        # No match found
        logger.warning(f"No matching pattern found for target column: {target_column}")
        return None, 0.0

    def _store_valid_values_in_s3(
        self, target_column: str, valid_values: List[str]
    ) -> str:
        """Store valid values for a column in S3 and return the reference path.

        Args:
            target_column: Target column name
            valid_values: List of valid values for the column

        Returns:
            S3 path to the stored valid values
        """
        if not valid_values:
            return ""

        # Create a unique key for this column's valid values
        timestamp = int(time.time())
        s3_key = f"transform_metadata/valid_values/{target_column}_{timestamp}.json"

        # Convert valid values to a JSON string
        valid_values_json = json.dumps(valid_values)

        # Upload to S3
        s3_client = boto3.client("s3")
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=valid_values_json,
            ContentType="application/json",
        )

        logger.info(
            f"Stored {len(valid_values)} valid values for {target_column} at s3://{S3_BUCKET}/{s3_key}"
        )
        return f"s3://{S3_BUCKET}/{s3_key}"

    def _generate_closest_match_sql(
        self, source_column: str, target_column: str, valid_values: List[str]
    ) -> str:
        """Generate SQL that maps source values to the closest match in valid_values.

        Args:
            source_column: Source column name
            target_column: Target column name
            valid_values: List of valid values for mapping

        Returns:
            SQL expression with reference to valid values
        """
        # If no source column or no valid values, return NULL or direct mapping
        if not source_column:
            return f"NULL AS `{target_column}`"

        if not valid_values:
            return f"`{source_column}` AS `{target_column}`"

        # Filter string values
        string_values = [v for v in valid_values if isinstance(v, str)]
        if not string_values:
            return f"`{source_column}` AS `{target_column}`"

        # Store valid values in S3 and get reference
        s3_reference = self._store_valid_values_in_s3(target_column, string_values)

        sql = f"/* VALID_VALUES_REF:{s3_reference} */ TRIM(`{source_column}`) AS `{target_column}`"

        return sql

    def _parse_batch_sql_response(
        self, content: str, transformations_data: List[Dict[str, Any]]
    ) -> List[str]:
        """Parse batch SQL response and return list of SQL expressions."""
        lines = content.split("\n")
        sql_expressions = []

        for i, data in enumerate(transformations_data):
            target_column = data["target_column"]
            source_column = data.get("source_column")
            valid_values = data.get("valid_values", [])
            has_valid_values = data.get("has_valid_values", False)
            found_sql = None

            # Check if this column has a special operation (split/combine)
            if target_column in self.column_operations:
                operation = self.column_operations[target_column]
                position = operation.get("position", 0)

                # Generate SQL based on the operation type
                found_sql = self._generate_split_column_sql(
                    operation["source_column"],
                    target_column,
                    operation["operation"],
                    operation.get("position", 0),
                    operation.get("total_parts", 2),
                )
                sql_expressions.append(found_sql)
                logger.info(
                    f"Generated column operation SQL for {target_column}: {found_sql}"
                )
                continue

            # If no source column match was found, always use NULL
            if not source_column:
                found_sql = f"NULL AS `{target_column}`"
                sql_expressions.append(found_sql)
                continue

            # Look for numbered SQL expression
            pattern = rf"{i+1}\.\s*(.+)"
            for line in lines:
                match = re.search(pattern, line)
                if match:
                    sql_expr = match.group(1).strip()
                    # Clean SQL expression
                    sql_expr = re.sub(
                        r"^```sql\s*|\s*```\s*$", "", sql_expr, flags=re.MULTILINE
                    )

                    # Check if the expression contains placeholder text or is empty
                    if (
                        any(
                            placeholder in sql_expr
                            for placeholder in [
                                "[SQL_EXPRESSION]",
                                "**SQL_EXPRESSION**",
                                "SQL_EXPRESSION",
                            ]
                        )
                        or sql_expr == "NULL"
                        or not sql_expr.strip()
                    ):
                        # Use source column directly if available
                        sql_expr = f"`{source_column}`"

                    # Remove any existing AS clauses to prevent double aliasing
                    sql_expr = re.sub(
                        r'\s+AS\s+[`"]?\w+[`"]?', "", sql_expr, flags=re.IGNORECASE
                    )

                    # Add the alias
                    found_sql = f"{sql_expr} AS `{target_column}`"
                    break

            # Fallback if not found
            if not found_sql:
                found_sql = f"`{source_column}` AS `{target_column}`"

            # Final validation to ensure we don't have an empty expression
            if (
                found_sql.strip() == f"AS `{target_column}`"
                or found_sql.strip() == f" AS `{target_column}`"
            ):
                found_sql = f"`{source_column}` AS `{target_column}`"

            # Add the SQL expression to the result list
            sql_expressions.append(found_sql)

        return sql_expressions

    def generate_column_transformation(
        self,
        source_column: str,
        target_column: str,
        valid_values: List[str],
        has_valid_values: bool = True,
    ) -> str:
        """
        Generate SQL transformation using Bedrock

        Args:
            source_column: Source column name
            target_column: Target column name
            valid_values: List of valid values for the column
            has_valid_values: Whether target column has actual values or just column name

        Returns:
            SQL transformation expression
        """
        # If target column has no values, just rename the source column
        if not has_valid_values or not valid_values:
            logger.info(
                f"Target column {target_column} has no values, creating simple rename transformation"
            )
            return f"`{source_column}` AS `{target_column}`"

        system_prompt = """
        You are an advanced SQL data transformation expert. Generate precise
        SQL transformations that:
        1. Convert source column to target column format
        2. Handle data type conversions
        3. Normalize values
        4. Manage NULL and edge cases
        5. Ensure data integrity
        6. Match values to the closest valid value in the provided list
        """

        user_prompt = f"""
        Transformation Requirements:
        - Source Column: {source_column}
        - Target Column: {target_column}
        - Valid Values: {valid_values}

        Provide:
        - SQL transformation expression that maps input values to EXACTLY match one of the valid values
        - Use CASE statements or other SQL constructs to ensure the output value is exactly one from the valid_values list
        - For input values not in the list, map to the closest matching valid value
        - Type casting
        - Value normalization
        - NULL handling strategy

        CRITICAL FORMATTING RULES:
        1. DO NOT include any 'AS' or column aliasing in your expressions
        2. Return only the transformation logic (e.g., TRIM(`source_column`) or CASE WHEN...)
        3. I will add the proper column aliasing later

        Output ONLY the SQL transformation expression without any aliasing.
        """

        try:
            response = self._bedrock_call_with_retry(
                system_prompt, user_prompt, max_tokens=500, temperature=0.4
            )

            content = response["output"]["message"]["content"][0]["text"]

            # Clean and validate SQL expression
            sql_expr = content.strip()
            sql_expr = re.sub(
                r"^```sql\s*|\s*```\s*\$", "", sql_expr, flags=re.MULTILINE
            )

            # Remove any existing AS clauses to prevent double aliasing
            sql_expr = re.sub(
                r'\s+AS\s+[`"]?\w+[`"]?', "", sql_expr, flags=re.IGNORECASE
            )

            # Add the alias
            sql_expr = f"{sql_expr} AS `{target_column}`"

            logger.info(f"Generated SQL for {target_column}: {sql_expr}")
            return sql_expr

        except Exception as e:
            logger.error(f"SQL Generation Error for {target_column}: {e}")

            # Fallback SQL generation
            if source_column:
                if not has_valid_values or not valid_values:
                    fallback_sql = f"`{source_column}` AS `{target_column}`"
                else:
                    fallback_sql = f"TRIM(`{source_column}`) AS `{target_column}`"
            else:
                fallback_sql = f"NULL AS `{target_column}`"
            logger.warning(f"Using fallback SQL: {fallback_sql}")
            return fallback_sql

    def _validate_column_match(self, candidate: str, source_columns: List[str]) -> bool:
        """Validate if candidate column exists in source columns."""
        # Exact match
        if candidate in source_columns:
            return True

        # Case-insensitive match
        candidate_lower = candidate.lower()
        for col in source_columns:
            if col.lower() == candidate_lower:
                return True

        # Partial match (candidate is substring of actual column)
        for col in source_columns:
            if candidate_lower in col.lower() or col.lower() in candidate_lower:
                return True

        return False

    def _bedrock_call_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        max_retries: int = 3,
    ):
        """Make Bedrock call with exponential backoff retry for throttling."""
        for attempt in range(max_retries):
            try:
                response = self.bedrock_runtime.converse(
                    modelId=LLM_MODEL_ID,
                    system=[{"text": system_prompt}],
                    messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                    inferenceConfig={
                        "maxTokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                return response

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if (
                    error_code in ["ThrottlingException", "TooManyRequestsException"]
                    and attempt < max_retries - 1
                ):
                    # Exponential backoff with jitter
                    wait_time = (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Bedrock throttling on attempt {attempt + 1}, retrying in {wait_time:.2f}s"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    raise e
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Bedrock error on attempt {attempt + 1}: {e}, retrying in {wait_time:.2f}s"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    raise e

        raise Exception(f"Failed after {max_retries} attempts")


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
            return df, schema
        elif key.lower().endswith(".tsv"):
            logger.info(f"Parsing {key} as TSV schema")
            file = key.split("/")[-1].split(".")[0]
            schema_df = pd.read_csv(io.BytesIO(content), sep="\t")

            # Get the dictionary data
            response = s3_client.get_object(
                Bucket=bucket,
                Key="transform_metadata/schema/GC_Dictionary_All_v6.0.4.tsv",
            )
            content = response["Body"].read()
            dictionary_df = pd.read_csv(io.BytesIO(content), sep="\t")

            # Filter dictionary to relevant entries
            filtered_dict = dictionary_df[
                (dictionary_df["Node"] == file)
                & (dictionary_df["Property"].isin(schema_df.columns))
            ]

            # Create result DataFrame with values and descriptions
            result_data = {}
            for col in schema_df.columns:
                result_data[col] = pd.Series([])
                result_data[f"{col}_description"] = pd.Series([])

            # Fill in values and descriptions from dictionary
            for _, row in filtered_dict.iterrows():
                col_name = row["Property"]
                if col_name in schema_df.columns:
                    # Add acceptable values
                    if pd.notna(row["Acceptable Values"]):
                        if isinstance(row["Acceptable Values"], str) and row[
                            "Acceptable Values"
                        ].startswith("["):
                            try:
                                values = ast.literal_eval(row["Acceptable Values"])
                            except:
                                values = [row["Acceptable Values"]]
                        else:
                            values = [row["Acceptable Values"]]
                        result_data[col_name] = pd.Series(values)

                    # Add descriptions
                    if pd.notna(row["Description"]):
                        result_data[f"{col_name}_description"] = pd.Series(
                            [row["Description"]]
                        )

            # Create the final DataFrame
            result_df = pd.DataFrame(result_data)

            # Save DataFrame to a temporary CSV file and upload to S3
            temp_file = "/tmp/result_data.csv"
            result_df.to_csv(temp_file, index=False)
            s3_output_key = f"transform_metadata/tmp/{file}_schema.csv"
            s3_client.upload_file(temp_file, bucket, s3_output_key)
            logger.info(f"Uploaded processed data to s3://{bucket}/{s3_output_key}")

            schema = {"columns": result_df.columns.tolist()}
            logger.info(f"TSV Table: {result_df}")
            logger.info(f"TSV Columns: {schema}")
            return result_df, schema
        else:
            raise
    except Exception as e:
        logger.error(f"Error loading schema from S3: {str(e)}")
        raise


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Main Lambda handler for chunk translation

    Args:
        event: Lambda event with schema details
        context: Lambda context

    Returns:
        Dictionary with transformation details for all columns in chunk
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # In a Map state with S3 ItemReader, we get an array of Items
    chunk_task_path = None

    # Check if this is an S3 event from the Map state with Items array
    if "Items" in event and len(event["Items"]) > 0:
        # We're processing a batch of items, take the first one
        item = event["Items"][0]
        s3_key = item.get("Key")
        # Bucket is not included in the Items, use the environment variable
        s3_bucket = S3_BUCKET
        chunk_task_path = f"s3://{s3_bucket}/{s3_key}"
    # Check if this is a single S3 object
    elif "Key" in event:
        s3_key = event.get("Key")
        s3_bucket = S3_BUCKET
        chunk_task_path = f"s3://{s3_bucket}/{s3_key}"
    else:
        # If not from Map state, look for task_path directly
        chunk_task_path = event.get("source_table_path")

    if not chunk_task_path:
        raise ValueError("Missing required parameter: task_path")

    # Extract bucket and key from S3 paths
    if chunk_task_path.startswith("s3://"):
        parts = chunk_task_path.replace("s3://", "").split("/", 1)
        task_bucket = parts[0]
        task_key = parts[1]
    else:
        task_bucket = S3_BUCKET
        task_key = chunk_task_path

    # Load the chunk task first to get task_id and other info
    chunk_task = load_chunk_task(task_bucket, task_key)

    source_table_path = str(chunk_task.get("source_table_path")).strip("[]'")
    target_schema_path = chunk_task.get("target_schema_path")
    columns = chunk_task.get("columns", [])

    logger.info(f"Source Table Path: {source_table_path}")
    logger.info(f"Target Schema Path: {target_schema_path}")
    logger.info(
        f"Processing {len(columns)} columns: {[col['name'] for col in columns]}"
    )

    if not all([source_table_path, target_schema_path, columns]):
        raise ValueError("Missing required parameters")

    # Process target schema path
    if target_schema_path.startswith("s3://"):
        parts = target_schema_path.replace("s3://", "").split("/", 1)
        schema_bucket = parts[0]
        schema_key = parts[1]
    else:
        schema_bucket = S3_BUCKET
        schema_key = target_schema_path

    s3_client = boto3.client("s3")
    try:
        s3_client.head_object(Bucket=schema_bucket, Key=schema_key)
    except:
        schema_key = schema_key.replace(".csv", ".tsv")
    logger.info(f"Schema Bucket: {schema_bucket}, Schema Key: {schema_key}")

    if source_table_path.startswith("s3://"):
        parts = source_table_path.replace("s3://", "").split("/", 1)
        source_bucket = parts[0]
        source_key = parts[1]
    else:
        source_bucket = S3_BUCKET
        source_key = source_table_path

    # Load source and target schemas
    source_df, source_schema = load_schema(source_bucket, source_key)
    target_df, target_schema = load_schema(schema_bucket, schema_key)

    # Fix: Extract column lists properly
    source_columns = source_schema["columns"]
    target_columns = target_schema["columns"]

    logger.info(f"Loaded source columns: {source_columns}")
    logger.info(f"Loaded target columns: {target_columns}")

    # Initialize translator
    translator = ColumnTranslator()

    # Extract target column names for batch processing
    target_column_names = [col["name"] for col in columns]

    # Batch semantic column matching
    logger.info(
        f"Performing batch semantic matching for {len(target_column_names)} columns"
    )
    batch_matches = translator.batch_semantic_column_match(
        source_columns, target_column_names, target_df, source_df
    )

    # Prepare transformation data for batch processing
    transformations_data = []
    for i, (target_column, best_match, confidence) in enumerate(batch_matches):
        # Validate match with threshold
        if not best_match or confidence < CONFIDENCE_THRESHOLD:
            logger.warning(
                f"No confident match found for {target_column} (confidence: {confidence}%, threshold: {CONFIDENCE_THRESHOLD}%)."
            )
            best_match = None

        # Get valid values for the target column
        valid_values = []
        has_valid_values = False
        try:
            if target_column in target_df.columns:
                # Get all unique values - we need all of them for accurate mapping
                valid_values = target_df[target_column].dropna().unique().tolist()
                has_valid_values = len(valid_values) > 0 and not all(
                    pd.isna(v) or str(v).strip() == "" for v in valid_values
                )
                logger.info(
                    f"Found {len(valid_values)} valid values for {target_column}, has_valid_values: {has_valid_values}"
                )
                logger.info(f"Preview valid values: {valid_values[:15]}")
            else:
                logger.warning(
                    f"Target column {target_column} not found in target schema"
                )
        except Exception as e:
            logger.error(f"Error extracting valid values for {target_column}: {e}")
            valid_values = []
            has_valid_values = False

        # Handle comma-separated column matches
        valid_source_column = None
        if best_match:
            if "," in best_match:
                # Check if all individual columns exist
                columns = [col.strip() for col in best_match.split(",")]
                if all(col in source_columns for col in columns):
                    valid_source_column = best_match
            else:
                # Single column check
                if best_match in source_columns:
                    valid_source_column = best_match

        # Prepare transformation data
        transformations_data.append(
            {
                "source_column": valid_source_column,
                "target_column": target_column,
                "valid_values": valid_values,
                "has_valid_values": has_valid_values,
                "valid_values_count": len(valid_values),
            }
        )

    # Batch generate SQL transformations
    logger.info(
        f"Generating batch SQL transformations for {len(transformations_data)} columns"
    )
    sql_transformations = translator.batch_generate_column_transformations(
        transformations_data
    )

    # Combine results
    transformations = []
    for i, sql_transformation in enumerate(sql_transformations):
        target_column = transformations_data[i]["target_column"]
        source_column = transformations_data[i]["source_column"]
        valid_values = transformations_data[i].get("valid_values", [])
        has_valid_values = transformations_data[i].get("has_valid_values", False)

        # Handle NULL transformations for unmatched columns
        if not source_column:
            sql_transformation = f"NULL AS `{target_column}`"
        # Check if source_column contains multiple columns (comma-separated)
        elif source_column and "," in source_column:
            # Parse multiple columns and combine with underscores
            columns = [col.strip() for col in source_column.split(",")]
            # Filter out any columns that don't exist in source_columns
            valid_columns = [col for col in columns if col in source_columns]
            if valid_columns:
                if len(valid_columns) == 1:
                    sql_transformation = f"`{valid_columns[0]}` AS `{target_column}`"
                else:
                    # Combine multiple columns with underscores
                    concat_expr = " || '_' || ".join(
                        [f"`{col}`" for col in valid_columns]
                    )
                    sql_transformation = f"{concat_expr} AS `{target_column}`"
                logger.info(
                    f"Generated multi-column combination for {target_column}: {valid_columns}"
                )
            else:
                sql_transformation = f"NULL AS `{target_column}`"
                logger.warning(
                    f"No valid columns found in multi-column match for {target_column}: {columns}"
                )
        # Check if the transformation is NULL, empty, or contains placeholder text
        elif (
            not sql_transformation
            or sql_transformation.strip().upper().startswith("NULL")
            or any(
                placeholder in sql_transformation
                for placeholder in [
                    "[SQL_EXPRESSION]",
                    "**SQL_EXPRESSION**",
                    "SQL_EXPRESSION",
                ]
            )
            or sql_transformation.strip().startswith(f"AS `{target_column}`")
            or f" AS `{target_column}`" == sql_transformation.strip()
        ):
            # Generate proper transformation based on available data
            if has_valid_values and valid_values:
                sql_transformation = translator._generate_closest_match_sql(
                    source_column, target_column, valid_values
                )
                logger.info(f"Generated valid values mapping for {target_column}")
            else:
                # Direct column mapping
                sql_transformation = f"`{source_column}` AS `{target_column}`"
                logger.info(f"Generated direct mapping for {target_column}")
        # Check if the transformation doesn't already handle valid values mapping
        elif (
            has_valid_values
            and valid_values
            and not "VALID_VALUES_REF" in sql_transformation
            and source_column
        ):
            # If the AI-generated SQL doesn't seem to handle valid values, enhance it
            logger.info(
                f"Enhancing transformation for {target_column} to use valid values mapping"
            )
            sql_transformation = translator._generate_closest_match_sql(
                source_column, target_column, valid_values
            )

        # Create a compact transformation object without the full valid_values list
        transformations.append(
            {
                "target_column": target_column,
                "sql_transformation": sql_transformation,
                "valid_values_count": transformations_data[i].get(
                    "valid_values_count", 0
                ),
            }
        )

        logger.info(f"Final transformation for {target_column}: {sql_transformation}")

    result = {
        "transformations": transformations,
        "source_table_path": source_table_path,
        "target_schema": [col for col in target_columns],
    }

    return result
