# Clients

This package provides clients for interacting with the curator workflows API endpoints:

- **Extract Metadata**: Extract structured metadata from documents
- **Transform Metadata**: Transform tables to match target schemas
- **Fix Metadata**: Fix invalid values in tabular data

## Usage

### Extract Metadata

```python
import sys
sys.path.append('path/to/client/src')
from extract_client import ExtractMetadataClient
from utils import detailed_status_callback

# Using the client directly
client = ExtractMetadataClient()
result = client.extract_metadata(
    source='local',
    file_path="/path/to/document.pdf",
    schema_name="nf"
)

# Access the extracted metadata
if "data" in result:
    metadata_df = result["data"]
    print(metadata_df.head())
```

### Extract Metadata with Entity Filenames

```python
import sys
sys.path.append('path/to/client/src')
from extract_client import ExtractMetadataClient
from utils import extract_entity_filenames_from_csv

# Extract entity filenames from a CSV file
entity_filenames = extract_entity_filenames_from_csv("/path/to/ground_truth.csv")

# Extract metadata with entity filenames
client = ExtractMetadataClient()
result = client.extract_metadata(
    source='local',
    file_path="/path/to/document.pdf",
    schema_name="nf",
    filenames=entity_filenames
)

# Check which entities were found
if "found_entities" in result:
    print(f"Found entities: {result['found_entities']}")
    print(f"Missing entities: {result['missing_entities']}")
```

### Process Multiple Files

```python
import sys
import glob
sys.path.append('path/to/client/src')
from extract_client import ExtractMetadataClient
from utils import batch_status_callback, map_files_to_entities

# Get all PDF files in a directory
files = glob.glob("/path/to/documents/*.pdf")

# Create client
client = ExtractMetadataClient()

# Process all files in parallel
result = client.process_files(
    files=files,
    schema_name="nf",
    skip_extensions=[".tgz"],
    max_workers=5,
    callback=batch_status_callback
)

# Access the results
print(f"Processed {result['processed_files']} of {result['total_files']} files")
print(f"Status counts: {result['status_counts']}")
```

### Transform Metadata

```python
import sys
sys.path.append('path/to/client/src')
from transform_client import TransformMetadataClient

# Using the client directly
client = TransformMetadataClient()
result = client.transform_metadata(
    file_path="/path/to/source.csv",
    schema="target_schema"
)

# Access the transformed data
if "data" in result:
    transformed_df = result["data"]
    print(transformed_df.head())

    # View column analysis
    if "column_analysis" in result:
        print(f"Original columns: {result['column_analysis']['original_columns']}")
        print(f"Transformed columns: {result['column_analysis']['transformed_columns']}")
        print(f"Added columns: {result['column_analysis']['added_columns']}")
        print(f"Removed columns: {result['column_analysis']['removed_columns']}")
```

### Fix Metadata

```python
import sys
sys.path.append('path/to/client/src')
from fix_client import FixMetadataClient

# Using the client directly
client = FixMetadataClient()
result = client.fix_metadata(
    file_path="/path/to/data_with_errors.csv",
    schema="sample_schema"
)

# Access the corrected data
if "data" in result:
    corrected_df = result["data"]
    print(corrected_df.head())

    # View correction summary
    if "corrections" in result:
        print(f"Total corrections: {result['correction_count']}")
        for column, details in result["corrections"].items():
            print(f"Column '{column}': {details['count']} corrections")
```

## Advanced Usage

### Custom Status Callback

You can provide a custom callback function to receive status updates during processing:

```python
def my_callback(status_data, attempt, max_attempts):
    status = status_data.get('status', 'UNKNOWN')
    print(f"Custom callback: Attempt {attempt}/{max_attempts} - Status: {status}")

    # Print detailed execution information if available
    execution_status = status_data.get('executionStatus', {})
    if execution_status:
        print(f"Current state: {execution_status.get('currentState', 'Unknown')}")

client = ExtractMetadataClient()
result = client.extract_metadata(
    source='local',
    file_path="/path/to/document.pdf",
    schema_name="nf",
    callback=my_callback
)
```

### Custom Output Path

You can specify a custom output path for the results:

```python
client = ExtractMetadataClient()
result = client.extract_metadata(
    source='local',
    file_path="/path/to/document.pdf",
    schema_name="nf",
    output_path="/path/to/output/extracted_metadata.csv"
)
```

### Configuring the Client

You can configure the client with custom API URL and API key:

```python
from extract_client import ExtractMetadataClient

client = ExtractMetadataClient(
    api_url="https://custom-api-url.com",
    api_key="your-api-key"
)
```

## Environment Variables

The clients will use the following environment variables if they are set:

- `API_URL`: The URL of the API
- `API_KEY`: The API key for authentication

You can set these variables in a `.env` file and load them using the `dotenv` package:

```python
from dotenv import load_dotenv
load_dotenv()
```
