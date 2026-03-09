# Step Functions Organization

This directory contains the AWS Step Functions definitions for the Curator workflows, organized for proper integration with CDK infrastructure.

## Directory Structure

```
step_functions/
├── README.md                          # This file
└── definitions/                       # Step function JSON definitions
    ├── extract_metadata.json          # Metadata extraction workflow
    ├── fix_metadata.json              # Metadata value correction workflow
    └── transform_metadata.json        # Table transformation workflow
```

## Workflow Descriptions

### 1. Extract Metadata (`extract_metadata.json`)

**Purpose**: Extracts metadata from PDF documents using Bedrock Data Automation and AI/LLM processing.

**Key Steps**:

- `PrepareS3Keys`: Prepares S3 keys for processing
- `InvokeDataAutomationAsync`: Invokes Bedrock Data Automation
- `ChunkTask`: Chunks the document based on character limits (keeping pages whole)
- `ProcessDocumentChunks`: Distributed map to process document chunks
- `ConsolidateResults`: Final consolidation into CSV format

**Lambda Functions Used**:

- `chunk_task`
- `create_table`
- `consolidate_results`

### 2. Fix Metadata (`fix_metadata.json`)

**Purpose**: Corrects invalid values in metadata tables using AI validation against a schema of allowed values.

**Key Steps**:

- `CreateColumnChunks`: Identifies invalid values by column
- `ProcessColumnChunks`: Distributed map to generate corrections for each column
- `ApplyCorrections`: Applies corrections to create a clean CSV

**Lambda Functions Used**:

- `create_col_chunks`
- `create_correction_key`
- `apply_corrections`

### 3. Table Transformation (`transform_metadata.json`)

**Purpose**: Transforms tables to match target schemas using AI.

**Key Steps**:

- `CreateColumnTranslationTasks`: Creates translation tasks for each target column
- `ColumnTranslationMap`: Distributed map to generate SQL operations per column
- `ConsolidateColumns`: Applies operations to create final transformed table

**Lambda Functions Used**:

- `create_col_translation_tasks`
- `translate_col`
- `consolidate_cols`

## Placeholder System

The JSON definitions use a consistent placeholder system that gets replaced by the CDK stack:

### Lambda Function Placeholders

- `${chunk_task_lambda_arn}`
- `${create_table_lambda_arn}`
- `${consolidate_results_lambda_arn}`
- `${create_col_chunks_lambda_arn}`
- `${create_correction_key_lambda_arn}`
- `${apply_corrections_lambda_arn}`
- `${create_col_translation_tasks_lambda_arn}`
- `${translate_col_lambda_arn}`
- `${consolidate_cols_lambda_arn}`

### Resource Placeholders

- `${s3_bucket_name}`: S3 bucket name for data storage

## CDK Integration

The step functions are integrated with CDK through the `StepFunctionsStack` class:

1. **Lambda Creation**: Each workflow's Lambda functions are created with proper IAM roles and S3 permissions
2. **Placeholder Replacement**: The `_replace_placeholders_in_definition()` method substitutes placeholders with actual ARNs
3. **State Machine Creation**: Step Functions are created using the processed definitions

## Key Improvements Made

### 1. **Organized Structure**

- Moved definitions to dedicated `definitions/` subdirectory
- Clear naming conventions and documentation

### 2. **Fixed Placeholder Mapping**

- Corrected mismatched Lambda function names between JSON and CDK
- Standardized placeholder naming convention (`*_lambda_arn`)
- Added S3 bucket name placeholder support

### 3. **Improved Step Function Syntax**

- Updated to use proper `Parameters` and `OutputPath` syntax
- Fixed S3 integration parameters for ItemReader
- Added proper state naming to avoid conflicts

### 4. **Enhanced Error Handling**

- Consistent retry policies across all Lambda invocations
- Proper error handling for distributed map operations

### 5. **Better Resource Management**

- Dynamic S3 bucket references instead of hardcoded values
- Proper IAM role assignment for all Lambda functions

## Usage

When deploying with CDK:

```bash
cd infra
cdk deploy GenAICuratorStepFunctionsStack
```

The stack will:

1. Create all required Lambda functions
2. Set up proper IAM roles and permissions
3. Replace placeholders in step function definitions
4. Deploy the state machines to AWS

## Migration Notes

If you have existing step function executions or references to the old JSON files:

1. **Old Files**: The original `*.json` files in the root can be safely removed after confirming the new structure works
2. **State Machine Names**: The CDK-created state machines will have consistent names:
   - `ExtractMetadataStateMachine`
   - `FixValuesStateMachine`
   - `TableTranslationStateMachine`
3. **Testing**: Test each workflow individually before removing old definitions

## Future Enhancements

Consider these improvements for future iterations:

1. **Environment-specific configurations**: Add dev/staging/prod variants
2. **Monitoring integration**: Add CloudWatch alarms and metrics
3. **Cost optimization**: Implement step function express workflows where appropriate
4. **Error notifications**: Add SNS integration for failure notifications
