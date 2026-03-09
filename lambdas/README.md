# Lambda Functions

This directory contains all Lambda functions used in the Curator workflows. The functions are organized into subdirectories based on their workflow.

## Directory Structure

```
lambdas/
├── README.md                          # This file
├── Makefile                           # Build and deployment utilities
├── extract_metadata/                  # Document processing workflow lambdas
│   ├── README.md                      # Workflow-specific documentation
│   ├── chunk_task/                    # Chunks task by document and expected filenames
│   ├── create_table/                  # Creates structured table rows from chunks
│   └── consolidate_results/           # Consolidates results into a CSV
├── fix_metadata/                      # Value correction workflow lambdas
│   ├── README.md                      # Workflow-specific documentation
│   ├── create_col_chunks/             # Identifies invalid values by column
│   ├── create_correction_key/         # Generates correction mappings
│   └── apply_corrections/             # Applies corrections to create clean CSV
├── transform_metadata/                # Table translation workflow lambdas
│   ├── README.md                      # Workflow-specific documentation
│   ├── create_col_translation_tasks/  # Creates translation tasks
│   ├── translate_col/                 # Generates SQL operations per column
│   └── consolidate_cols/              # Applies operations to create final table
├── generate_presigned_url/            # Generates presigned URLs for S3 uploads
└── get_task_status/                   # Retrieves status of workflow executions
```

## Workflow Overview

The Lambda functions are organized into three main workflows:

1. **Metadata extraction** (`extract_metadata/`): Extracts structured data from PDF documents using Bedrock Data Automation and AI/LLM processing.

2. **Value Correction** (`fix_metadata/`): Corrects invalid values in CSV tables using AI validation against a schema of allowed values.

3. **Table Translation** (`transform_metadata/`): Transforms tables to match target schemas using AI-generated SQL operations.

Additionally, there are utility Lambda functions for API integration and task management.

## Lambda Function Structure

Each Lambda function follows a consistent structure:

- `Dockerfile`: Container definition for the Lambda function
- `lambda_function.py`: Main entry point with the handler function
- Additional Python modules as needed

## Environment Variables

Common environment variables used across Lambda functions:

- `LOG_LEVEL`: Logging level (INFO, DEBUG, etc.)
- `LLM_MODEL_ID`: Bedrock model ID for AI operations
- `S3_BUCKET`: S3 bucket name for data storage

## Build and Deployment

The Makefile provides utilities for building and deploying the Lambda functions:

```bash
# Build all Lambda functions
make build

# Deploy all Lambda functions
make deploy

# Build and deploy a specific Lambda function
make build-<function_name>
make deploy-<function_name>
```

## Integration with Step Functions

The Lambda functions are integrated with Step Functions through the CDK stack in `infra/stacks/step_functions_stack.py`.
