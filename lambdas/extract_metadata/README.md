# Extract Metadata Lambda Functions

This directory contains Lambda functions for the extract_metadata workflow, which extracts structured metadata from documents.

## Overview

The extract_metadata workflow processes documents to extract structured metadata based on a schema. It uses Bedrock Data Automation to extract text from documents, chunks the document by page, generates structured table rows for each chunk, and consolidates the results into a single CSV file.

## Workflow Scenarios

The workflow now supports two scenarios:

### Scenario 1: With Entity Filenames

When a list of entity filenames is provided:

- The filenames are meaningful and named after entities in the document
- They define exactly what rows must be in the final result
- Metadata fields can be empty if not found in the document

This scenario is useful when you know exactly what entities should be in the output table, even if some metadata fields are empty.

### Scenario 2: Without Entity Filenames (Default)

When no list of filenames is provided:

- Entities are inferred from the document content
- The workflow continues with the current approach of extracting all entities found in the document

This is the original behavior and is useful when you want to extract all entities from the document.

## Lambda Functions

### chunk_task

This function processes the output from Bedrock Data Automation (BDA), extracts the markdown content from each page, and creates chunks of pages that stay under a specified character limit. It writes each chunk to S3 and returns the list of chunks for distributed processing.

### create_table

This function processes a chunk of document content, reads the relevant schema, and uses Bedrock to generate structured table rows. It now supports two modes:

- When entity filenames are provided, it generates rows for each entity, with metadata fields that can be empty if not found in the document
- When no entity filenames are provided, it infers entities from the document content

### consolidate_results

This function retrieves all results generated from distributed processing of document chunks, combines them into a structured dataset, creates a single CSV file with all rows, and generates a summary of the extraction results. It ensures all entities from the provided filenames are included in the final output, even if some metadata fields are empty.

## How to Use

### API Request

To use the extract_metadata endpoint with entity filenames, include the `entityFilenames` parameter in your request:

```json
{
  "schemaName": "nf",
  "fileType": "application/pdf",
  "fileExtension": "pdf",
  "workflow": "extract_metadata",
  "entityFilenames": ["MS02-2", "MS02-3", "HS11", "SYN_NF_001"]
}
```

### Using Ground Truth CSV Files

You can extract entity filenames from ground truth CSV files. These files typically contain a `name` column that can be used as entity filenames:

```python
import pandas as pd

# Path to the ground truth CSV file
ground_truth_path = "path/to/ground_truth/nf_1.csv"

# Read the CSV file
ground_truth_df = pd.read_csv(ground_truth_path)

# Extract the 'name' field from each row
entity_filenames = ground_truth_df['name'].tolist()
```

You can also combine multiple ground truth files:

```python
# Paths to multiple ground truth CSV files
ground_truth_paths = [
    "path/to/ground_truth/nf_1.csv",
    "path/to/ground_truth/nf_2.csv"
]

# Read and combine all CSV files
entity_filenames = []
for path in ground_truth_paths:
    df = pd.read_csv(path)
    entity_filenames.extend(df['name'].tolist())
```

### Example Notebook

See the `extract_metadata_with_entities_demo.ipynb` notebook in the `notebooks` directory for a complete example of how to use the extract_metadata endpoint with entity filenames.

## Schema

The schema defines the fields to extract from the document. The first field in the schema is used as the entity identifier field. For example, in the NF schema, the `SpecimenID` field is used as the entity identifier.

When entity filenames are provided, the workflow will ensure that rows exist for each entity, with the entity identifier field set to the entity filename. Other fields may be empty if the information is not found in the document.
