# Fix Values Lambda Functions

This directory contains the lambda functions that implement the `fix_values` step function. The step function is designed to correct invalid values in tabular data by identifying invalid values, generating corrections, and applying those corrections to produce a cleaned dataset.

## Overview

The `fix_values` step function processes tabular data (CSV files) stored in S3 and corrects values that don't conform to a predefined schema. The workflow consists of three main steps:

1. **Identify invalid values** in each column and chunk them if necessary
2. **Generate corrections** for invalid values using Bedrock AI
3. **Apply corrections** to the original table to create a cleaned version

## Lambda Functions

### 1. receive_table

**Purpose**: API endpoint that generates a pre-signed URL for uploading a table to S3.

**Input**:

- API Gateway request with table metadata
- Schema information for validation

**Output**:

- Pre-signed URL for uploading a CSV file to S3
- Task ID for tracking the processing status

**Implementation Details**:

- Generate a unique task ID for the table processing job
- Create a pre-signed URL for uploading the CSV file to S3
- Configure S3 event notifications to trigger the step function when the file is uploaded
- Return the pre-signed URL and task ID to the client

**Note**: This lambda is not part of the step function itself but serves as the entry point for the table correction workflow. When a file is uploaded using the pre-signed URL, it triggers the `fix_values` step function.

### 2. create_col_chunks

**Purpose**: Identify invalid values in each column and create chunks for distributed processing.

**Input**:

- S3 path to the CSV file
- S3 path to the schema file
- Configuration parameters (e.g., chunk size)

**Output**:

- S3 paths to chunk files containing invalid values for each column
- Metadata about the chunks (number of chunks, columns processed, etc.)

**Implementation Details**:

- Load the CSV file and schema from S3
- For each column with a defined set of valid values in the schema:
  - Identify values that don't match the schema
  - Count unique invalid values
  - If more than 500 unique invalid values exist, chunk them into smaller groups
- Write each chunk to S3 with metadata about the column and valid values
- Return information about all chunks for the Map state

### 3. create_correction_key

**Purpose**: Generate mappings from invalid values to valid values using Bedrock AI.

**Input**:

- S3 path to a chunk file containing invalid values
- Column name and description
- List of approved values from the schema
- Configuration for the Bedrock model

**Output**:

- A correction key (dictionary) mapping invalid values to valid values
- S3 path to the stored correction key

**Implementation Details**:

- Load the chunk file containing invalid values
- Prepare a prompt for Bedrock that includes:
  - Column description and context
  - List of approved values
  - List of invalid values that need correction
- Call Bedrock to generate mappings from invalid values to valid values
- Parse the response to create a correction key
- Store the correction key in S3
- Return the path to the correction key

### 4. apply_corrections

**Purpose**: Apply the generated correction keys to the original table.

**Input**:

- S3 path to the original CSV file
- S3 paths to all correction keys
- Output path for the corrected CSV

**Output**:

- S3 path to the corrected CSV file
- Statistics about corrections (number of values corrected, etc.)

**Implementation Details**:

- Load the original CSV file
- Load all correction keys from S3
- For each row in the CSV:
  - For each column with corrections:
    - If the value is in the correction key, replace it with the corrected value
  - Write the corrected row to the output CSV
- Generate statistics about the corrections
- Return the path to the corrected CSV and statistics

## Example Workflow

1. The step function starts with a table in S3 and a schema defining valid values for columns.
2. `create_col_chunks` identifies columns with invalid values and creates chunks for processing.
3. The Map state distributes the chunks to multiple `create_correction_key` executions.
4. Each `create_correction_key` execution generates mappings for a subset of invalid values.
5. `apply_corrections` combines all correction keys and applies them to the original table.
6. The corrected table is written to S3.

## Schema Format

The schema file should be a JSON file with column names as keys and arrays of valid values as values:

```json
{
  "Column1": ["Value1", "Value2", "Value3"],
  "Column2": ["ValueA", "ValueB", "ValueC"]
}
```

## Correction Key Format

Correction keys are JSON files mapping invalid values to valid values:

```json
{
  "InvalidValue1": "ValidValue1",
  "InvalidValue2": "ValidValue2",
  "typo": "correct spelling"
}
```

## Error Handling

Each lambda function includes error handling to catch and report issues:

- Schema validation errors
- S3 access errors
- Bedrock API errors
- Invalid response formats

Errors are logged and raised to allow the step function to handle retries or failure paths.
