# Data Directory

This directory contains schema definitions and utility scripts for the Curator workflows. Schemas are essential for all three workflows (extract, fix, transform) as they define the structure and valid values for metadata fields.

## Schema Files

### NF Schema

- **`NF.jsonld`**: The original NF (Neurofibromatosis) schema from the [NF-OSI metadata dictionary](https://github.com/nf-osi/nf-metadata-dictionary/blob/main/NF.jsonld).
- **`NF_schema_column_list_7_11_25.csv`**: A simplified list of columns from the NF schema.
- **`extract_metadata/nf/schema.json`**: Processed schema for the extract metadata workflow.
- **`fix_metadata/nf/schema.json`**: Processed schema for the fix metadata workflow, including valid values for each field.

## Utility Scripts

- **`create_simplified_nf_schema.py`**: Converts the full NF.jsonld schema into a simplified format that's more suitable for AI processing. It extracts essential fields, adds example values, and formats the schema for optimal use with LLMs.
- **`populate_bucket.sh`**: Uploads the processed schema files to the S3 bucket for use by the step functions.

## Schema Processing

The original NF schema (`NF.jsonld`) is comprehensive but has limitations for AI processing:
1. It's very large and contains many fields not needed for our use cases
2. It lacks example values that would help the LLM understand the expected format
3. It's not optimized for the specific needs of each workflow

The processing scripts address these issues by:
1. Extracting only the relevant fields for each workflow
2. Adding example values and descriptions where helpful
3. Formatting the schema differently for each workflow's specific needs
4. Creating a more concise representation that fits within LLM context windows

## Adding New Schemas

To add a new schema:

1. Place the original schema file in this directory
2. Create a processing script similar to `create_simplified_nf_schema.py`
3. Create subdirectories in `extract_metadata/` and `fix_metadata/` for the new schema
4. Run the processing script to generate the simplified schema files
5. Update `populate_bucket.sh` to upload the new schema files to S3

## Schema Structure

### Extract Metadata Schema

The extract metadata schema focuses on field descriptions and examples to help the LLM identify and extract relevant information from documents.

### Fix Metadata Schema

The fix metadata schema emphasizes valid values for each field, providing the LLM with the reference data needed to correct invalid values.

### Transform Metadata Schema

For transformation workflows, both source and target schemas are needed to map between different metadata formats.
