# This deliverable is considered developed content as defined in contract between BDF parties.


import json

from aws_cdk import CfnOutput, Fn, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct


class ApiStack(Stack):
    """Stack for API Gateway and related Lambda functions."""

    def __init__(
        self,
        scope: Construct,
        bucket: s3.Bucket,
        extract_metadata_state_machine: sfn.StateMachine,
        table_translation_state_machine: sfn.StateMachine,
        fix_metadata_state_machine: sfn.StateMachine,
        prefix: str,
        app_name: str,
        **kwargs,
    ) -> None:
        construct_id = f"{prefix}-{app_name}-ApiStack"
        super().__init__(scope, construct_id, **kwargs)

        # Store prefix and app_name for resource naming
        self.prefix = prefix
        self.app_name = app_name

        # Import Lambda functions from ComputeStack
        fix_metadata_lambda = lambda_.Function.from_function_attributes(
            self,
            "FixMetadataLambda",
            function_arn=Fn.import_value(
                f"{self.prefix}-{self.app_name}-FixMetadata-fix-metadata-Lambda-Arn"
            ),
            same_environment=True,
        )

        presigned_url_lambda = lambda_.Function.from_function_attributes(
            self,
            "PresignedUrlLambda",
            function_arn=Fn.import_value(
                f"{self.prefix}-{self.app_name}-Utility-presigned-url-Lambda-Arn"
            ),
            same_environment=True,
        )

        task_status_lambda = lambda_.Function.from_function_attributes(
            self,
            "TaskStatusLambda",
            function_arn=Fn.import_value(
                f"{self.prefix}-{self.app_name}-Utility-task-status-Lambda-Arn"
            ),
            same_environment=True,
        )

        # Create a role for API Gateway to invoke Step Functions
        api_step_functions_role = iam.Role(
            self,
            f"{self.prefix}-{self.app_name}-ApiStepFunctionsRole",
            role_name=f"{self.prefix}-{self.app_name}-ApiStepFunctionsRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
        )

        # Add permissions for API Gateway to invoke all Step Functions
        api_step_functions_role.add_to_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[
                    extract_metadata_state_machine.state_machine_arn,
                    table_translation_state_machine.state_machine_arn,
                    fix_metadata_state_machine.state_machine_arn,
                ],
            )
        )

        # Create a role for API Gateway to invoke Lambda functions
        api_lambda_role = iam.Role(
            self,
            f"{self.prefix}-{self.app_name}-ApiLambdaRole",
            role_name=f"{self.prefix}-{self.app_name}-ApiLambdaRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
        )

        # Add permissions for API Gateway to invoke Lambda functions
        api_lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    fix_metadata_lambda.function_arn,
                    presigned_url_lambda.function_arn,
                    task_status_lambda.function_arn,
                ],
            )
        )

        # Note: State machine ARNs for task_status_lambda are now set in the ComputeStack
        # Permissions to access the state machines are granted in the ComputeStack

        # Get the state machine names for exporting
        extract_metadata_name = extract_metadata_state_machine.state_machine_name
        table_translation_name = table_translation_state_machine.state_machine_name

        # Export state machine ARNs for the task_status_lambda to use
        CfnOutput(
            self,
            "ExtractMetadataStateMachineArn",
            value=extract_metadata_state_machine.state_machine_arn,
            export_name=f"{self.prefix}-{self.app_name}-ExtractMetadata-StateMachine-Arn",
        )

        CfnOutput(
            self,
            "TableTranslationStateMachineArn",
            value=table_translation_state_machine.state_machine_arn,
            export_name=f"{self.prefix}-{self.app_name}-TableTranslation-StateMachine-Arn",
        )

        CfnOutput(
            self,
            "FixMetadataStateMachineArn",
            value=fix_metadata_state_machine.state_machine_arn,
            export_name=f"{self.prefix}-{self.app_name}-FixMetadata-StateMachine-Arn",
        )

        # Create CloudWatch Log Group for API Gateway
        api_log_group = logs.LogGroup(
            self,
            f"{self.prefix}-{self.app_name}-ApiGatewayAccessLogs",
            log_group_name=f"/aws/apigateway/{self.prefix}-{self.app_name}-Api",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create API Gateway with logging enabled
        api = apigw.RestApi(
            self,
            f"{self.prefix}-{self.app_name}-API",
            rest_api_name=f"{self.prefix}-{self.app_name}-API",
            description=f"API for {self.app_name}",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "X-Api-Key"],
            ),
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                access_log_destination=apigw.LogGroupLogDestination(api_log_group),
                access_log_format=apigw.AccessLogFormat.clf(),
            ),
        )

        # Create request validator for all endpoints
        request_validator = api.add_request_validator(
            "RequestValidator",
            validate_request_body=True,
            validate_request_parameters=True,
        )

        # Define request models for each endpoint
        # Common upload request model
        upload_request_model = api.add_model(
            "UploadRequestModel",
            content_type="application/json",
            model_name="UploadRequestModel",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT7,
                title="UploadRequestModel",
                type=apigw.JsonSchemaType.OBJECT,
                required=["schemaName", "fileExtension"],
                properties={
                    "schemaName": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "fileType": apigw.JsonSchema(
                        type=apigw.JsonSchemaType.STRING, default="application/zip"
                    ),
                    "fileExtension": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "entityFilenames": apigw.JsonSchema(
                        type=apigw.JsonSchemaType.ARRAY,
                        items=apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    ),
                },
            ),
        )

        # Extract metadata request model
        extract_metadata_model = api.add_model(
            "ExtractMetadataModel",
            content_type="application/json",
            model_name="ExtractMetadataModel",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT7,
                title="ExtractMetadataModel",
                type=apigw.JsonSchemaType.OBJECT,
                required=["bucket", "document_key", "schema_key"],
                properties={
                    "bucket": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "document_key": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "schema_key": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "output_prefix": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "filenames": apigw.JsonSchema(
                        type=apigw.JsonSchemaType.ARRAY,
                        items=apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    ),
                },
            ),
        )

        # Fix metadata request model
        fix_metadata_model = api.add_model(
            "FixMetadataModel",
            content_type="application/json",
            model_name="FixMetadataModel",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT7,
                title="FixMetadataModel",
                type=apigw.JsonSchemaType.OBJECT,
                required=["sourceTablePath", "outputPrefix", "schemaKey"],
                properties={
                    "sourceTablePath": apigw.JsonSchema(
                        type=apigw.JsonSchemaType.STRING
                    ),
                    "outputPrefix": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "schemaKey": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                },
            ),
        )

        # Transform metadata request model
        transform_metadata_model = api.add_model(
            "TransformMetadataModel",
            content_type="application/json",
            model_name="TransformMetadataModel",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT7,
                title="TransformMetadataModel",
                type=apigw.JsonSchemaType.OBJECT,
                required=["bucket", "key", "jobId"],
                properties={
                    "bucket": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "key": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "jobId": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                },
            ),
        )

        # Create API Key
        api_key = api.add_api_key(f"{self.prefix}-{self.app_name}-ApiKey")

        # Create usage plan
        plan = api.add_usage_plan(
            f"{self.prefix}-{self.app_name}-UsagePlan",
            name=f"{self.prefix}-{self.app_name}-UsagePlan",
            throttle=apigw.ThrottleSettings(
                rate_limit=10,
                burst_limit=20,
            ),
        )

        plan.add_api_key(api_key)
        plan.add_api_stage(
            stage=api.deployment_stage,
        )

        # Create the main metadata resource
        metadata_resource = api.root.add_resource("metadata")

        # Create extract resource under metadata
        extract_resource = metadata_resource.add_resource("extract")

        # Create the integration for extract workflow - using StartExecution action for asynchronous execution
        extract_integration = apigw.AwsIntegration(
            service="states",
            action="StartExecution",
            options=apigw.IntegrationOptions(
                credentials_role=api_step_functions_role,
                request_templates={
                    "application/json": json.dumps(
                        {
                            "input": "$util.escapeJavaScript($input.json('$'))",
                            "stateMachineArn": extract_metadata_state_machine.state_machine_arn,
                        }
                    )
                },
                integration_responses=[
                    {
                        "statusCode": "200",
                        "responseTemplates": {
                            "application/json": json.dumps(
                                {
                                    "executionArn": "$util.parseJson($input.body).executionArn",
                                    "startDate": "$util.parseJson($input.body).startDate",
                                }
                            )
                        },
                    }
                ],
                passthrough_behavior=apigw.PassthroughBehavior.NEVER,
            ),
        )

        # Add the POST method to start extraction workflow
        extract_resource.add_method(
            "POST",
            extract_integration,
            method_responses=[{"statusCode": "200"}],
            api_key_required=True,
            request_models={"application/json": extract_metadata_model},
            request_validator=request_validator,
        )

        # Add upload endpoint for extract workflow
        extract_upload_resource = extract_resource.add_resource("upload")
        extract_upload_resource.add_method(
            "POST",
            apigw.LambdaIntegration(
                presigned_url_lambda,
                credentials_role=api_lambda_role,
                request_templates={
                    "application/json": '{"workflow": "extract_metadata", "schemaName": $input.json("$.schemaName"), "fileType": $input.json("$.fileType"), "fileExtension": $input.json("$.fileExtension")}'
                },
            ),
            api_key_required=True,
            request_models={"application/json": upload_request_model},
            request_validator=request_validator,
        )

        # Create fix resource under metadata
        fix_resource = metadata_resource.add_resource("fix")

        # Create the integration for fix workflow - using StartExecution action for asynchronous execution
        fix_integration = apigw.AwsIntegration(
            service="states",
            action="StartExecution",
            options=apigw.IntegrationOptions(
                credentials_role=api_step_functions_role,
                request_templates={
                    "application/json": json.dumps(
                        {
                            "input": "$util.escapeJavaScript($input.json('$'))",
                            "stateMachineArn": fix_metadata_state_machine.state_machine_arn,
                        }
                    )
                },
                integration_responses=[
                    {
                        "statusCode": "200",
                        "responseTemplates": {
                            "application/json": json.dumps(
                                {
                                    "executionArn": "$util.parseJson($input.body).executionArn",
                                    "startDate": "$util.parseJson($input.body).startDate",
                                }
                            )
                        },
                    }
                ],
                passthrough_behavior=apigw.PassthroughBehavior.NEVER,
            ),
        )

        # Add the POST method to start fix workflow
        fix_resource.add_method(
            "POST",
            fix_integration,
            method_responses=[{"statusCode": "200"}],
            api_key_required=True,
            request_models={"application/json": fix_metadata_model},
            request_validator=request_validator,
        )

        # Add upload endpoint for fix workflow
        fix_upload_resource = fix_resource.add_resource("upload")
        fix_upload_resource.add_method(
            "POST",
            apigw.LambdaIntegration(
                presigned_url_lambda,
                credentials_role=api_lambda_role,
                request_templates={
                    "application/json": '{"workflow": "fix_metadata", "schemaName": $input.json("$.schemaName"), "fileType": $input.json("$.fileType"), "fileExtension": $input.json("$.fileExtension")}'
                },
            ),
            api_key_required=True,
            request_models={"application/json": upload_request_model},
            request_validator=request_validator,
        )

        # Create transform resource under metadata
        transform_resource = metadata_resource.add_resource("transform")

        # Create the integration for transform workflow
        transform_integration = apigw.AwsIntegration(
            service="states",
            action="StartExecution",
            options=apigw.IntegrationOptions(
                credentials_role=api_step_functions_role,
                request_templates={
                    "application/json": json.dumps(
                        {
                            "input": "$util.escapeJavaScript($input.json('$'))",
                            "stateMachineArn": table_translation_state_machine.state_machine_arn,
                        }
                    )
                },
                integration_responses=[
                    {
                        "statusCode": "200",
                        "responseTemplates": {
                            "application/json": json.dumps(
                                {
                                    "executionArn": "$util.parseJson($input.body).executionArn",
                                    "startDate": "$util.parseJson($input.body).startDate",
                                }
                            )
                        },
                    }
                ],
                passthrough_behavior=apigw.PassthroughBehavior.NEVER,
            ),
        )

        # Add the POST method to start transform workflow
        transform_resource.add_method(
            "POST",
            transform_integration,
            method_responses=[{"statusCode": "200"}],
            api_key_required=True,
            request_models={"application/json": transform_metadata_model},
            request_validator=request_validator,
        )

        # Add upload endpoint for transform workflow
        transform_upload_resource = transform_resource.add_resource("upload")
        transform_upload_resource.add_method(
            "POST",
            apigw.LambdaIntegration(
                presigned_url_lambda,
                credentials_role=api_lambda_role,
                request_templates={
                    "application/json": '{"workflow": "transform_metadata", "schemaName": $input.json("$.schemaName"), "fileType": $input.json("$.fileType"), "fileExtension": $input.json("$.fileExtension")}'
                },
            ),
            api_key_required=True,
            request_models={"application/json": upload_request_model},
            request_validator=request_validator,
        )

        # Create tasks resource for task status
        tasks_resource = api.root.add_resource("tasks")
        task_id_resource = tasks_resource.add_resource("{executionArn}")
        task_id_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                task_status_lambda, credentials_role=api_lambda_role
            ),
            api_key_required=True,
            request_parameters={"method.request.path.executionArn": True},
            request_validator=request_validator,
        )
