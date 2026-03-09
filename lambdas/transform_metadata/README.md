# Table Translation Lambda Functions

This directory contains the AWS Lambda functions used in the Table Translation Step Function workflow. The workflow transforms an input table into a target schema by generating and applying SQL operations for each column.

## Workflow Overview

The Table Translation workflow consists of the following steps:

1. Create translation tasks for each column in the target schema
2. Process column tasks in parallel using a distributed Map state to generate SQL operations
3. Apply the generated operations to create the final translated table

## Lambda Functions

### create_col_translation_tasks

**Purpose**: Analyze the target schema and create translation tasks for columns in chunks.

**Input**:

- `jobId`: Unique identifier for this translation task
- `bucket`: S3 bucket containing the source table
- `key`: S3 key of the source table

**Output**:

- `task_id`: The task identifier
- `chunk_tasks`: List of column chunk tasks, each containing:
  - `chunk_index`: Index of the chunk
  - `task_path`: S3 path where the chunk task is stored
- `source_table_path`: S3 path to the source table
- `target_schema_path`: S3 path to the target schema
- `translation_tasks_prefix`: S3 prefix for all translation tasks

**Implementation Details**:

- Load the target schema from S3
- Group columns into chunks for efficient processing
- For each chunk, create a task object with column metadata
- Store each chunk task in S3 with a unique path
- Return the S3 prefix for the Map state to process

### translate_col

**Purpose**: Generate SQL operations to create target columns from source columns.

**Input**:

- S3 object containing chunk task details with:
  - `columns`: List of target columns to translate
  - `source_table_path`: S3 path to the source table
  - `target_schema_path`: S3 path to the target schema

**Output**:

- `transformations`: List of column transformations, each containing:
  - `target_column`: Name of the target column
  - `sql_transformation`: SQL operation to generate the target column
  - `valid_values_count`: Number of valid values for the column
- `source_table_path`: S3 path to the source table
- `target_schema`: List of target column names

**Implementation Details**:

- Load source and target schemas from S3
- Use semantic column matching to find the best source column for each target column
- Use Amazon Bedrock to generate SQL transformations for each column
- Handle column splitting and special operations
- Store valid values in S3 for semantic matching during consolidation
- Return SQL operations with confidence scores

### consolidate_cols

**Purpose**: Apply all column operations to create the final translated table.

**Input**:

- Results from the Map state containing all column transformations

**Output**:

- `translated_table_path`: S3 path to the final translated table
- `success`: Boolean indicating success or failure
- `stats`: Statistics about the translation (columns translated, rows processed, etc.)

**Implementation Details**:

- Load the source table into a pandas DataFrame
- Apply each SQL operation to create the corresponding target columns
- Use semantic matching with Amazon Bedrock for mapping values to valid values
- Handle special SQL operations like SUBSTRING_INDEX, TRIM, etc.
- Save the final translated table to S3
- Return statistics about the translation process

## Error Handling

Each lambda function implements proper error handling:

1. Validates all input parameters
2. Handles missing or malformed data gracefully
3. Logs detailed error information
4. Uses retry policies in the Step Function definition
5. Raises appropriate exceptions for the Step Function to catch and handle

## Environment Variables

- `LOG_LEVEL`: Logging level (default: INFO)
- `S3_BUCKET`: S3 bucket for storing task data and results
- `LLM_MODEL_ID`: Amazon Bedrock model ID for AI operations (default: amazon.nova-pro-v1:0)
- `CONFIDENCE_THRESHOLD`: Threshold for semantic matching confidence (default: 70)
- `SAMPLE_ROWS`: Number of rows to sample from source table (default: 10)
- `CHUNK_SIZE`: Number of columns per chunk (default: 5)
- `SEMANTIC_MATCH_ENABLED`: Whether to use semantic matching (default: true)

## Dependencies

- AWS Lambda Powertools for logging and tracing
- Pandas for data manipulation
- AWS SDK for S3 and Bedrock operations
- Regular expressions for SQL parsing

## Next Steps:

- Update file names/location logic for schemas and dictionary files to follow your file naming mechanism
- Add schema description for source tables for LLM in batch_semantic_column_match function to use
- Add S3 lifecycle to valid values and tmp folder to delete temporary files needed for workflow
