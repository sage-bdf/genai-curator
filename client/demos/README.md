# Curator Workflows Demos

This directory contains demonstration notebooks for the Curator workflows client libraries. These notebooks showcase how to use the client libraries to interact with the Curator workflows API for extracting, fixing, and transforming metadata.

## Prerequisites

Before running these demos, ensure you have:

1. Set up your environment as described in the [setup documentation](../../documentation/setup.md)
2. Installed the client library requirements:
   ```bash
   pip install -r ../requirements.txt
   ```
3. Configured your API credentials in a `.env` file or environment variables:
   ```
   API_URL=<your-api-url>
   API_KEY=<your-api-key>
   ```

## Available Demos

### Extract Metadata

Located in the `extract_metadata/` directory, this demo shows how to:

- Extract structured metadata from PDF documents
- Process multiple files in parallel
- Work with entity filenames for targeted extraction
- Analyze and validate extraction results

To run:

```bash
cd extract_metadata
jupyter notebook extract_metadata.ipynb
```

### Fix Metadata

Located in the `fix_metadata/` directory, this demo shows how to:

- Correct invalid values in metadata tables
- Compare corrected data with original data
- Evaluate correction accuracy
- Analyze correction patterns

To run:

```bash
cd fix_metadata
jupyter notebook fix_metadata_demo.ipynb
```

For evaluation:

```bash
jupyter notebook fix_metadata_evaluation.ipynb
```

### Transform Metadata

Located in the `transform_metadata/` directory, this demo shows how to:

- Transform metadata tables from one schema to another
- Analyze column mappings
- Validate transformation results

To run:

```bash
cd transform_metadata
jupyter notebook transform_metadata.ipynb
```

## Data Files

Each demo directory contains sample data files for testing:

- `extract_metadata/data/`: Sample PDF documents
- `fix_metadata/data/`: Sample CSV files with invalid values
- `transform_metadata/data/`: Sample CSV files for schema transformation

## Output

Demo notebooks save their output to their respective output directories:

- `extract_metadata/output/`: Extracted metadata CSV files
- `fix_metadata/output/`: Corrected metadata CSV files
- `transform_metadata/output/`: Transformed metadata CSV files
