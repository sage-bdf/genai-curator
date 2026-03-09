# API Reference

This document provides a comprehensive reference for Curator workflows API endpoints.

## Base URL

All API endpoints are relative to:

```
https://<api-id>.execute-api.<region>.amazonaws.com/prod
```

## Authentication

All API endpoints require an API key to be included in the request header:

```
x-api-key: <your-api-key>
```

## Endpoints

### Metadata Extraction

#### Start Extraction Workflow

```
POST /metadata/extract
```

Starts a workflow to extract metadata from a document.

**Request Body:**

```json
{
  "schemaName": "string", // Name of the target schema (e.g., "nf")
  "s3Key": "string", // S3 key of the uploaded document (optional if using upload endpoint)
  "fileType": "string" // MIME type of the document (e.g., "application/pdf")
}
```

**Response:**

```json
{
  "executionArn": "string", // ARN of the Step Function execution
  "startDate": "string" // ISO timestamp of when the execution started
}
```

#### Get Upload URL for Extraction

```
POST /metadata/extract/upload
```

Generates a pre-signed URL for uploading a document for metadata extraction.

**Request Body:**

```json
{
  "schemaName": "string", // Name of the target schema (e.g., "nf")
  "fileType": "string", // MIME type of the document (e.g., "application/pdf")
  "fileExtension": "string" // File extension (e.g., "pdf")
}
```

**Response:**

```json
{
  "uploadUrl": "string", // Pre-signed URL for uploading the document
  "s3Key": "string" // S3 key where the document will be stored
}
```

### Metadata Fixing

#### Start Fix Workflow

```
POST /metadata/fix
```

Starts a workflow to fix invalid values in a metadata table.

**Request Body:**

```json
{
  "schemaName": "string", // Name of the target schema (e.g., "nf")
  "s3Key": "string", // S3 key of the uploaded table (optional if using upload endpoint)
  "fileType": "string" // MIME type of the table (e.g., "text/csv")
}
```

**Response:**

```json
{
  "executionArn": "string", // ARN of the Step Function execution
  "startDate": "string" // ISO timestamp of when the execution started
}
```

#### Get Upload URL for Fixing

```
POST /metadata/fix/upload
```

Generates a pre-signed URL for uploading a metadata table for fixing.

**Request Body:**

```json
{
  "schemaName": "string", // Name of the target schema (e.g., "nf")
  "fileType": "string", // MIME type of the table (e.g., "text/csv")
  "fileExtension": "string" // File extension (e.g., "csv")
}
```

**Response:**

```json
{
  "uploadUrl": "string", // Pre-signed URL for uploading the table
  "s3Key": "string" // S3 key where the table will be stored
}
```

### Metadata Transformation

#### Start Transform Workflow

```
POST /metadata/transform
```

Starts a workflow to transform a metadata table from one schema to another.

**Request Body:**

```json
{
  "schemaName": "string", // Name of the target schema (e.g., "nf")
  "s3Key": "string", // S3 key of the uploaded table (optional if using upload endpoint)
  "fileType": "string" // MIME type of the table (e.g., "text/csv")
}
```

**Response:**

```json
{
  "executionArn": "string", // ARN of the Step Function execution
  "startDate": "string" // ISO timestamp of when the execution started
}
```

#### Get Upload URL for Transformation

```
POST /metadata/transform/upload
```

Generates a pre-signed URL for uploading a metadata table for transformation.

**Request Body:**

```json
{
  "schemaName": "string", // Name of the target schema (e.g., "nf")
  "fileType": "string", // MIME type of the table (e.g., "text/csv")
  "fileExtension": "string" // File extension (e.g., "csv")
}
```

**Response:**

```json
{
  "uploadUrl": "string", // Pre-signed URL for uploading the table
  "s3Key": "string" // S3 key where the table will be stored
}
```

### Task Status

#### Get Task Status

```
GET /tasks/{executionArn}
```

Gets the status of a task execution.

**Path Parameters:**

- `executionArn`: ARN of the Step Function execution

**Response:**

```json
{
  "status": "string", // Status of the execution (e.g., "RUNNING", "SUCCEEDED", "FAILED")
  "executionStatus": {
    // Detailed execution status
    "currentState": "string", // Current state of the execution
    "progress": {
      // Progress information (if available)
      "total": "number", // Total number of items
      "processed": "number" // Number of processed items
    }
  },
  "output": {
    // Output of the execution (if available)
    "s3Key": "string", // S3 key of the output file
    "downloadUrl": "string" // Pre-signed URL for downloading the output file
  },
  "error": {
    // Error information (if execution failed)
    "message": "string", // Error message
    "cause": "string" // Error cause
  }
}
```

## Workflow

A typical workflow for using the API involves the following steps:

1. **Get Upload URL**:
   - Call the appropriate upload endpoint (`/metadata/extract/upload`, `/metadata/fix/upload`, or `/metadata/transform/upload`)
   - Receive a pre-signed URL and S3 key

2. **Upload File**:
   - Upload the file to the pre-signed URL using an HTTP PUT request

3. **Start Workflow**:
   - Call the appropriate workflow endpoint (`/metadata/extract`, `/metadata/fix`, or `/metadata/transform`) with the S3 key
   - Receive an execution ARN

4. **Poll for Status**:
   - Periodically call the task status endpoint (`/tasks/{executionArn}`) with the execution ARN
   - When the status is `SUCCEEDED`, retrieve the output file using the provided download URL

## Error Handling

The API uses standard HTTP status codes to indicate the success or failure of requests:

- `200 OK`: The request was successful
- `400 Bad Request`: The request was invalid or missing required parameters
- `401 Unauthorized`: The API key was missing or invalid
- `404 Not Found`: The requested resource was not found
- `500 Internal Server Error`: An error occurred on the server

Error responses include a JSON body with details about the error:

```json
{
  "message": "string", // Error message
  "code": "string" // Error code
}
```
