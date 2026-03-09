# Setup Guide

This guide provides instructions for setting up and deploying the Curator workflows.


```bash
aws configure sso

export AWS_ACCESS_KEY_ID="XXXXXXX"
export AWS_SECRET_ACCESS_KEY="XXXXXXX"
export AWS_SESSION_TOKEN="XXXXXXX"
```


## Prerequisites

- AWS CLI installed and configured with appropriate credentials
- Python 3.10 or higher
- Node.js 14 or higher (required for AWS CDK)
- AWS CDK installed globally: `npm install -g aws-cdk`
- Docker (for building Lambda container images)

## Local Development Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd genai-curator
```

2. Set up the client environment:

```bash
cd client
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up the infrastructure environment:

```bash
cd ../infra
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

1. Update the `cdk.json` file in the infra directory with your specific stack prefix:

```json
{
  "app": "python app.py",
  "context": {
    "prefix": "jeff-dev",
    ...
  }
}
```

## Deploying the Infrastructure

1. Bootstrap AWS CDK (if not already done):

```bash
cd ../infra
cdk bootstrap
```

2. Deploy all stacks:

```bash
make deploy
```

This will deploy the following stacks:

- GenAICuratorStorageStack: S3 bucket
- GenAICuratorStepFunctionsStack: Step functions and related Lambda functions
- GenAICuratorApiStack: API Gateway and API endpoint Lambda functions

## Populating buckets with schemas for reference

Extract and fix metadata rely on schema reference files. The NF schema files can be uploaded up-front with this script:

```sh
cd ../data
sh ./populate_bucket.sh ntyj-genaicurator-bucket
```

## Running the Demos

1. Create a `.env` file in the client directory with the following variables (See AWS console for API Gateway's native key):

```
API_URL=<your-api-url>
API_KEY=<your-api-key>
```

2. Activate the client environment:

```bash
cd ../client
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Run the extract metadata demo:

```bash
cd demos/extract_metadata
# if the jupyter is not installed: try python -m pip install notebook ipykernel
jupyter notebook extract_metadata.ipynb
```

4. Run the fix metadata demo:

```bash
cd ../fix_metadata
jupyter notebook fix_metadata_demo.ipynb
```

5. Run the transform metadata demo:

```bash
cd ../transform_metadata
jupyter notebook transform_metadata.ipynb
```

## Testing the API

After deployment, you can test the API using the following commands:

1. Get the API URL and API Key from the AWS Console (API Gateway service)

2. Test the extract_metadata endpoint:

```bash
curl -X POST \
  https://<api-id>.execute-api.<region>.amazonaws.com/prod/metadata/extract \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: <api-key>' \
  -d '{"schemaName": "nf", "fileType": "application/pdf"}'
```

3. Test the fix_metadata endpoint:

```bash
curl -X POST \
  https://<api-id>.execute-api.<region>.amazonaws.com/prod/metadata/fix \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: <api-key>' \
  -d '{"schemaName": "nf", "fileType": "text/csv"}'
```

4. Test the transform_metadata endpoint:

```bash
curl -X POST \
  https://<api-id>.execute-api.<region>.amazonaws.com/prod/metadata/transform \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: <api-key>' \
  -d '{"schemaName": "nf", "fileType": "text/csv"}'
```

## Cleanup

To destroy all stacks:

```bash
cd infra
make destroy
```

## Troubleshooting

1. **Permission Issues**: Ensure your AWS credentials have sufficient permissions to create all the required resources.

2. **Deployment Failures**: Check the CloudFormation console for detailed error messages.

3. **Lambda Function Errors**: Check CloudWatch Logs for Lambda function logs.

4. **API Gateway Issues**: Ensure the API Key is correctly set in the request header.

5. **Client Connection Issues**: Verify that the API_URL and API_KEY in your .env file are correct.
