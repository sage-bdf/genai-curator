#!/bin/bash

# Script to recursively upload the extract_metadata and fix_metadata folders to an S3 bucket
# Usage: ./populate_bucket.sh <s3-bucket-name>

set -e  # Exit immediately if a command exits with a non-zero status

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if the bucket name is provided
if [ $# -ne 1 ]; then
    echo "Usage: $0 <s3-bucket-name>"
    echo "Example: $0 my-metadata-bucket"
    exit 1
fi

BUCKET_NAME=$1
SCRIPT_DIR="$(dirname "$0")"
EXTRACT_SOURCE_DIR="${SCRIPT_DIR}/extract_metadata"
FIX_SOURCE_DIR="${SCRIPT_DIR}/fix_metadata"

# Check if the extract_metadata directory exists
if [ ! -d "$EXTRACT_SOURCE_DIR" ]; then
    echo "Error: Source directory '$EXTRACT_SOURCE_DIR' does not exist."
    exit 1
fi

# Create fix_metadata directory structure if it doesn't exist
mkdir -p "${FIX_SOURCE_DIR}/nf"

# Copy the original NF.jsonld file to fix_metadata/nf/schema.json (renaming it)
echo "Copying original NF.jsonld file to fix_metadata/nf/schema.json..."
cp "${SCRIPT_DIR}/NF.jsonld" "${FIX_SOURCE_DIR}/nf/schema.json"

echo "Starting upload of '$EXTRACT_SOURCE_DIR' to s3://$BUCKET_NAME/extract_metadata/"

# Upload the extract_metadata files recursively
aws s3 cp "$EXTRACT_SOURCE_DIR" "s3://$BUCKET_NAME/extract_metadata/" --recursive

# Check if the upload was successful
if [ $? -eq 0 ]; then
    echo "Extract metadata upload completed successfully!"
    echo "Files are now available at s3://$BUCKET_NAME/extract_metadata/"
else
    echo "Error: Extract metadata upload failed."
    exit 1
fi

echo "Starting upload of '$FIX_SOURCE_DIR' to s3://$BUCKET_NAME/fix_metadata/"

# Upload the fix_metadata files recursively
aws s3 cp "$FIX_SOURCE_DIR" "s3://$BUCKET_NAME/fix_metadata/" --recursive

# Check if the upload was successful
if [ $? -eq 0 ]; then
    echo "Fix metadata upload completed successfully!"
    echo "Files are now available at s3://$BUCKET_NAME/fix_metadata/"
else
    echo "Error: Fix metadata upload failed."
    exit 1
fi

echo "All uploads completed successfully!"
