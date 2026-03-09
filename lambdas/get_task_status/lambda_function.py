# This deliverable is considered developed content as defined in contract between BDF parties.


"""Lambda function that retrieves the status of processing tasks.

This module provides an API endpoint to check the status of document processing,
table translation, or value correction tasks using Step Functions execution ARNs.
It allows clients to query task progress, retrieve results when available, and handle error states.
"""

import json
from typing import Any, Dict

import boto3
from aws_lambda_powertools import Logger
from botocore.exceptions import ClientError

# Configure logging with Lambda Powertools
logger = Logger(service="get_task_status")

# Initialize AWS clients
sfn_client = boto3.client("stepfunctions")


def is_execution_arn(execution_arn: str) -> bool:
    """Check if the provided string is a valid Step Functions execution ARN.

    Args:
        execution_arn: The string to check

    Returns:
        True if the string is an execution ARN, False otherwise
    """
    return (
        execution_arn.startswith("arn:aws:states:") and ":execution:" in execution_arn
    )


def get_execution_status(execution_arn: str) -> Dict[str, Any]:
    """Get the status of a Step Function execution.

    Args:
        execution_arn: The execution ARN to look up

    Returns:
        Dictionary containing execution status information
    """
    try:
        # Get basic execution information
        execution_response = sfn_client.describe_execution(executionArn=execution_arn)

        # Get execution history to determine current state
        history_response = sfn_client.get_execution_history(
            executionArn=execution_arn,
            reverseOrder=True,
            maxResults=10,  # Limit to recent events for performance
        )

        # Find the most recent state entered event
        current_state = None
        current_state_entered_time = None
        for event in history_response.get("events", []):
            if event.get("type") == "StateEntered":
                current_state = event.get("stateEnteredEventDetails", {}).get("name")
                current_state_entered_time = event.get("timestamp")
                break

        # Build response with detailed information
        result = {
            "status": execution_response["status"],
            "startDate": execution_response["startDate"].isoformat(),
            "stopDate": (
                execution_response.get("stopDate", "").isoformat()
                if execution_response.get("stopDate")
                else None
            ),
            "output": (
                json.loads(execution_response.get("output", "{}"))
                if execution_response.get("output")
                else None
            ),
            "currentState": current_state,
            "currentStateEnteredAt": (
                current_state_entered_time.isoformat()
                if current_state_entered_time
                else None
            ),
        }

        # Add execution history summary
        state_transitions = []
        for event in reversed(history_response.get("events", [])):
            if event.get("type") == "StateEntered":
                state_name = event.get("stateEnteredEventDetails", {}).get("name")
                timestamp = event.get("timestamp")
                if state_name and timestamp:
                    state_transitions.append(
                        {"state": state_name, "enteredAt": timestamp.isoformat()}
                    )

        if state_transitions:
            result["stateTransitions"] = state_transitions

        return result
    except ClientError as e:
        logger.error(f"Error retrieving execution status: {str(e)}")
        return {"status": "UNKNOWN", "error": str(e)}


def lambda_handler(event, context):
    """Retrieve the status of a processing task.

    This function queries the task status from Step Functions using an execution ARN,
    and returns information about the task's progress, results, or error state.

    Args:
        event: API Gateway event containing the execution ARN in path parameters
        context: Lambda context object

    Returns:
        JSON response with task status information
    """
    logger.info(f"event: {event}")

    try:
        # Extract execution ARN from path parameters
        path_params = event.get("pathParameters", {}) or {}
        execution_arn = path_params.get("executionArn")

        if not execution_arn:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {"error": "Missing required parameter: executionArn"}
                ),
            }

        # Validate the execution ARN format
        if not is_execution_arn(execution_arn):
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {"error": f"Invalid execution ARN format: {execution_arn}"}
                ),
            }

        # Get execution status from Step Functions
        execution_status = get_execution_status(execution_arn)

        # Prepare response with execution information
        response_data = {
            "executionArn": execution_arn,
            "status": execution_status.get("status", "UNKNOWN"),
            "executionStatus": execution_status,
        }

        # Update status based on execution status
        if execution_status.get("status") == "SUCCEEDED":
            response_data["status"] = "COMPLETED"
        elif execution_status.get("status") == "FAILED":
            response_data["status"] = "FAILED"
        elif execution_status.get("status") == "RUNNING":
            response_data["status"] = "PROCESSING"

        # Include output location if available
        if execution_status.get("output"):
            output_data = execution_status.get("output", {})
            if isinstance(output_data, str):
                try:
                    output_data = json.loads(output_data)
                except json.JSONDecodeError:
                    output_data = {}

            # Handle case where outputLocation is directly provided
            if "outputLocation" in output_data:
                response_data["outputLocation"] = output_data["outputLocation"]
            # Handle case where bucket and csvKey are provided separately
            elif "bucket" in output_data and "csvKey" in output_data:
                bucket = output_data["bucket"]
                csv_key = output_data["csvKey"]
                response_data["outputLocation"] = f"s3://{bucket}/{csv_key}"

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(response_data),
        }

    except Exception as e:
        logger.exception(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
