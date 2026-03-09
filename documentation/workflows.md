# Workflows

This project implements three main workflows, each defined within a step function and triggered via API Gateway. Each workflow follows a similar pattern of file upload, processing, and status tracking.

## Extract Metadata from a Research Paper

The workflow for extracting metadata from research papers involves the following steps:

1. **Request Upload URL**:
   - Client calls `POST /metadata/extract/upload` with:
     ```json
     {
       "schemaName": "string", // e.g., "nf"
       "fileType": "string", // e.g., "application/pdf"
       "fileExtension": "string" // e.g., "pdf"
     }
     ```
   - API returns a pre-signed URL and S3 key:
     ```json
     {
       "uploadUrl": "string",
       "s3Key": "string"
     }
     ```

2. **Upload Document**:
   - Client uploads the PDF document to the pre-signed URL using an HTTP PUT request

3. **Start Extraction**:
   - After uploading, client calls `POST /metadata/extract` with:
     ```json
     {
       "schemaName": "string",
       "s3Key": "string", // S3 key from upload response
       "fileType": "string"
     }
     ```
   - API returns an execution ARN:
     ```json
     {
       "executionArn": "string",
       "startDate": "string"
     }
     ```

4. **Track Progress**:
   - Client polls `GET /tasks/{executionArn}` every 5 seconds with the execution ARN
   - Lambda checks the step function status and returns:
     ```json
     {
       "status": "string", // e.g., "RUNNING", "SUCCEEDED", "FAILED"
       "executionStatus": {
         "currentState": "string",
         "progress": {
           "total": "number",
           "processed": "number"
         }
       }
     }
     ```

5. **Processing**:
   - Document is processed by Bedrock Data Automation to extract contents
   - Text is chunked to stay within model context limits
   - Each chunk is processed to extract structured metadata
   - Results are consolidated into a single CSV file

6. **Get Results**:
   - When status is `SUCCEEDED`, the response includes:
     ```json
     {
       "output": {
         "s3Key": "string",
         "downloadUrl": "string" // Pre-signed URL for downloading the output file
       }
     }
     ```
   - Client downloads the extracted metadata CSV using the provided URL

## Fix Metadata Values

The workflow for correcting invalid values in metadata tables involves the following steps:

1. **Request Upload URL**:
   - Client calls `POST /metadata/fix/upload` with:
     ```json
     {
       "schemaName": "string", // e.g., "nf"
       "fileType": "string", // e.g., "text/csv"
       "fileExtension": "string" // e.g., "csv"
     }
     ```
   - API returns a pre-signed URL and S3 key:
     ```json
     {
       "uploadUrl": "string",
       "s3Key": "string"
     }
     ```

2. **Upload Table**:
   - Client uploads the CSV table to the pre-signed URL using an HTTP PUT request

3. **Start Fix Workflow**:
   - After uploading, client calls `POST /metadata/fix` with:
     ```json
     {
       "schemaName": "string",
       "s3Key": "string", // S3 key from upload response
       "fileType": "string"
     }
     ```
   - API returns an execution ARN:
     ```json
     {
       "executionArn": "string",
       "startDate": "string"
     }
     ```

4. **Track Progress**:
   - Client polls `GET /tasks/{executionArn}` every 5 seconds with the execution ARN
   - Lambda checks the step function status and returns progress information

5. **Processing**:
   - Input table is analyzed to identify invalid values
   - Invalid values are processed in parallel to generate corrections
   - AI-generated corrections are applied to create a cleaned table
   - Correction statistics and details are provided in the output

6. **Get Results**:
   - When status is `SUCCEEDED`, the client downloads the fixed metadata CSV
   - The fixed table includes corrections for all invalid values based on the schema's approved values

## Transform Metadata to a New Schema

The workflow for transforming metadata tables between schemas involves the following steps:

1. **Request Upload URL**:
   - Client calls `POST /metadata/transform/upload` with:
     ```json
     {
       "schemaName": "string", // e.g., "nf"
       "fileType": "string", // e.g., "text/csv"
       "fileExtension": "string" // e.g., "csv"
     }
     ```
   - API returns a pre-signed URL and S3 key:
     ```json
     {
       "uploadUrl": "string",
       "s3Key": "string"
     }
     ```

2. **Upload Table**:
   - Client uploads the CSV table to the pre-signed URL using an HTTP PUT request

3. **Start Transform Workflow**:
   - After uploading, client calls `POST /metadata/transform` with:
     ```json
     {
       "schemaName": "string",
       "s3Key": "string", // S3 key from upload response
       "fileType": "string"
     }
     ```
   - API returns an execution ARN:
     ```json
     {
       "executionArn": "string",
       "startDate": "string"
     }
     ```

4. **Track Progress**:
   - Client polls `GET /tasks/{executionArn}` every 5 seconds with the execution ARN
   - Lambda checks the step function status and returns progress information

5. **Processing**:
   - Source table is analyzed to understand its structure
   - Translation tasks are created for each target column
   - AI generates SQL operations to transform source columns to target schema
   - Operations are applied to create the final transformed table

6. **Get Results**:
   - When status is `SUCCEEDED`, the client downloads the transformed metadata CSV
   - The transformed table conforms to the target schema structure and controlled vocabularies
