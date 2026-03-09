# This deliverable is considered developed content as defined in contract between BDF parties.


import json

from aws_cdk import Fn, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from constructs import Construct


class StepFunctionsStack(Stack):
    """Stack for Step Functions and related Lambda functions."""

    def __init__(
        self,
        scope: Construct,
        bucket: s3.Bucket,
        bedrock_data_automation_project_arn: str,
        prefix: str,
        app_name: str,
        **kwargs,
    ) -> None:
        construct_id = f"{prefix}-{app_name}-StepFunctionsStack"
        super().__init__(scope, construct_id, **kwargs)

        # Store prefix and app_name for resource naming
        self.prefix = prefix
        self.app_name = app_name

        # Store the Bedrock Data Automation project ARN
        self.bedrock_data_automation_project_arn = bedrock_data_automation_project_arn

        # Import Lambda functions from ComputeStack
        extract_metadata_lambdas = self._import_extract_metadata_lambdas()
        transform_metadata_lambdas = self._import_transform_metadata_lambdas()
        fix_metadata_lambdas = self._import_fix_metadata_lambdas()

        # Create Step Functions
        self.extract_metadata_state_machine = (
            self._create_extract_metadata_state_machine(
                extract_metadata_lambdas, bucket
            )
        )
        self.table_translation_state_machine = (
            self._create_table_translation_state_machine(
                transform_metadata_lambdas, bucket
            )
        )
        self.fix_metadata_state_machine = self._create_fix_metadata_state_machine(
            fix_metadata_lambdas, bucket
        )

    def _create_extract_metadata_state_machine(
        self, lambdas: dict, bucket: s3.Bucket
    ) -> sfn.StateMachine:
        """Create the metadata extraction state machine."""
        # Load the step function definition from the JSON file
        with open("../step_functions/definitions/extract_metadata.json", "r") as f:
            definition = json.load(f)

        # Create IAM role for the state machine with Lambda invoke permissions
        extract_metadata_role = iam.Role(
            self,
            f"{self.prefix}-{self.app_name}-ExtractMetadataStateMachineRole",
            role_name=f"{self.prefix}-{self.app_name}-ExtractMetadataStateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaRole"
                )
            ],
        )

        # Add specific Lambda invoke permissions
        extract_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    lambda_fn.function_arn
                    for lambda_fn in lambdas.values()
                    if lambda_fn
                ],
            )
        )

        # Add S3 permissions
        extract_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:ListBucket",
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:PutObjectAcl",
                ],
                resources=[
                    bucket.bucket_arn,
                    f"{bucket.bucket_arn}/*",
                ],
            )
        )

        # Add Bedrock model invocation permissions
        extract_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                ],
                resources=["*"],
            )
        )

        # Add Bedrock Data Automation permissions
        # Using wildcard for data automation resources as they have different ARN formats
        extract_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:GetDataAutomationStatus",
                    "bedrock:InvokeDataAutomationAsync",
                    "bedrock:BedrockDataAutomationRuntime",
                ],
                resources=["*"],
            )
        )

        # Add distributed map permissions
        extract_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "states:StartExecution",
                    "states:DescribeExecution",
                    "states:StopExecution",
                ],
                resources=[
                    f"arn:aws:states:{self.region}:{self.account}:stateMachine:{self.prefix}-{self.app_name}-*",
                    f"arn:aws:states:{self.region}:{self.account}:execution:{self.prefix}-{self.app_name}-*:*",
                ],
            )
        )

        # Add states:StartExecution permission
        extract_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[
                    f"arn:aws:states:{self.region}:{self.account}:stateMachine:{self.prefix}-{self.app_name}-*"
                ],
            )
        )

        # Create the state machine from the definition with the role
        state_machine = sfn.StateMachine(
            self,
            f"{self.prefix}-{self.app_name}-ExtractMetadataStateMachine",
            state_machine_name=f"{self.prefix}-{self.app_name}-ExtractMetadataStateMachine",
            definition_body=sfn.DefinitionBody.from_string(
                json.dumps(
                    self._replace_placeholders_in_definition(
                        definition, lambdas, bucket
                    )
                )
            ),
            role=extract_metadata_role,
        )

        return state_machine

    def _create_table_translation_state_machine(
        self, lambdas: dict, bucket: s3.Bucket
    ) -> sfn.StateMachine:
        """Create the table translation state machine."""
        # Load the step function definition from the JSON file
        with open("../step_functions/definitions/transform_metadata.json", "r") as f:
            definition = json.load(f)

        # Create IAM role for the state machine with Lambda invoke permissions
        table_translation_role = iam.Role(
            self,
            f"{self.prefix}-{self.app_name}-TableTranslationStateMachineRole",
            role_name=f"{self.prefix}-{self.app_name}-TableTranslationStateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaRole"
                )
            ],
        )

        # Add specific Lambda invoke permissions
        table_translation_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    lambda_fn.function_arn
                    for lambda_fn in lambdas.values()
                    if lambda_fn
                ],
            )
        )

        # Add S3 permissions
        table_translation_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:ListBucket",
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:PutObjectAcl",
                ],
                resources=[
                    bucket.bucket_arn,
                    f"{bucket.bucket_arn}/*",
                ],
            )
        )

        # Add states:StartExecution permission
        table_translation_role.add_to_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[
                    f"arn:aws:states:{self.region}:{self.account}:stateMachine:{self.prefix}-{self.app_name}-*"
                ],
            )
        )

        # Create the state machine from the definition with the role
        state_machine = sfn.StateMachine(
            self,
            f"{self.prefix}-{self.app_name}-TableTranslationStateMachine",
            state_machine_name=f"{self.prefix}-{self.app_name}-TableTranslationStateMachine",
            definition_body=sfn.DefinitionBody.from_string(
                json.dumps(
                    self._replace_placeholders_in_definition(
                        definition, lambdas, bucket
                    )
                )
            ),
            role=table_translation_role,
        )

        return state_machine

    def _create_fix_metadata_state_machine(
        self, lambdas: dict, bucket: s3.Bucket
    ) -> sfn.StateMachine:
        """Create the fix metadata state machine."""
        # Load the step function definition from the JSON file
        with open("../step_functions/definitions/fix_metadata.json", "r") as f:
            definition = json.load(f)

        # Create IAM role for the state machine with Lambda invoke permissions
        fix_metadata_role = iam.Role(
            self,
            f"{self.prefix}-{self.app_name}-FixMetadataStateMachineRole",
            role_name=f"{self.prefix}-{self.app_name}-FixMetadataStateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaRole"
                )
            ],
        )

        # Add specific Lambda invoke permissions
        fix_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    lambda_fn.function_arn
                    for lambda_fn in lambdas.values()
                    if lambda_fn
                ],
            )
        )

        # Add S3 permissions
        fix_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:ListBucket",
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:PutObjectAcl",
                ],
                resources=[
                    bucket.bucket_arn,
                    f"{bucket.bucket_arn}/*",
                ],
            )
        )

        # Create the state machine from the definition with the role
        state_machine = sfn.StateMachine(
            self,
            f"{self.prefix}-{self.app_name}-FixMetadataStateMachine",
            state_machine_name=f"{self.prefix}-{self.app_name}-FixMetadataStateMachine",
            definition_body=sfn.DefinitionBody.from_string(
                json.dumps(
                    self._replace_placeholders_in_definition(
                        definition, lambdas, bucket
                    )
                )
            ),
            role=fix_metadata_role,
        )

        return state_machine

    def _import_extract_metadata_lambdas(self) -> dict:
        """Import Lambda functions for extract_metadata workflow from ComputeStack."""
        lambdas = {}

        # Import Lambda functions using CloudFormation exports
        lambdas["chunk_task"] = lambda_.Function.from_function_arn(
            self,
            "ChunkTaskLambda",
            Fn.import_value(
                f"{self.prefix}-{self.app_name}-ExtractMetadata-chunk-task-Lambda-Arn"
            ),
        )

        lambdas["create_table"] = lambda_.Function.from_function_arn(
            self,
            "CreateTableLambda",
            Fn.import_value(
                f"{self.prefix}-{self.app_name}-ExtractMetadata-create-table-Lambda-Arn"
            ),
        )

        lambdas["consolidate_results"] = lambda_.Function.from_function_arn(
            self,
            "ConsolidateResultsLambda",
            Fn.import_value(
                f"{self.prefix}-{self.app_name}-ExtractMetadata-consolidate-results-Lambda-Arn"
            ),
        )

        return lambdas

    def _import_transform_metadata_lambdas(self) -> dict:
        """Import Lambda functions for transform_metadata workflow from ComputeStack."""
        lambdas = {}

        # Import Lambda functions using CloudFormation exports
        lambdas["create_col_translation_tasks"] = lambda_.Function.from_function_arn(
            self,
            "CreateColTranslationTasksLambda",
            Fn.import_value(
                f"{self.prefix}-{self.app_name}-TransformMetadata-create-col-translation-tasks-Lambda-Arn"
            ),
        )

        lambdas["translate_col"] = lambda_.Function.from_function_arn(
            self,
            "TranslateColLambda",
            Fn.import_value(
                f"{self.prefix}-{self.app_name}-TransformMetadata-translate-col-Lambda-Arn"
            ),
        )

        lambdas["consolidate_cols"] = lambda_.Function.from_function_arn(
            self,
            "ConsolidateColsLambda",
            Fn.import_value(
                f"{self.prefix}-{self.app_name}-TransformMetadata-consolidate-cols-Lambda-Arn"
            ),
        )

        return lambdas

    def _import_fix_metadata_lambdas(self) -> dict:
        """Import Lambda functions for fix_metadata workflow from ComputeStack."""
        lambdas = {}

        # Import Lambda function using CloudFormation exports
        lambdas["fix_metadata"] = lambda_.Function.from_function_arn(
            self,
            "FixMetadataLambda",
            Fn.import_value(
                f"{self.prefix}-{self.app_name}-FixMetadata-fix-metadata-Lambda-Arn"
            ),
        )

        return lambdas

    def _replace_placeholders_in_definition(
        self,
        definition: dict,
        lambdas: dict,
        bucket: s3.Bucket,
    ) -> dict:
        """Replace placeholders in the step function definition with actual ARNs and resource names."""
        # Create a deep copy of the definition to avoid modifying the original
        definition_copy = json.loads(json.dumps(definition))

        # Remove static job ID generation for extract_metadata.json
        # This will be handled at runtime by the PrepareS3Keys state

        # Replace S3 bucket name placeholder
        definition_str = json.dumps(definition_copy)
        definition_str = definition_str.replace("${s3_bucket_name}", bucket.bucket_name)

        # Replace region and account ID placeholders in DataAutomationProfileArn
        definition_str = definition_str.replace("<REGION>", self.region)
        definition_str = definition_str.replace("<ACCOUNT_ID>", self.account)

        # Replace Bedrock Data Automation project ARN placeholder
        definition_str = definition_str.replace(
            "${bedrock_data_automation_project_arn}",
            self.bedrock_data_automation_project_arn,
        )

        # Create mapping from placeholder names to Lambda ARNs
        lambda_arn_mappings = {
            # Extract metadata workflow mappings - used in extract_metadata.json
            "chunk_task_lambda_arn": lambdas.get("chunk_task"),
            "create_table_lambda_arn": lambdas.get("create_table"),
            "consolidate_results_lambda_arn": lambdas.get("consolidate_results"),
            # Transform metadata workflow mappings - used in table_translation.json
            "create_col_translation_tasks_lambda_arn": lambdas.get(
                "create_col_translation_tasks"
            ),
            "translate_col_lambda_arn": lambdas.get("translate_col"),
            "consolidate_cols_lambda_arn": lambdas.get("consolidate_cols"),
            # Fix metadata workflow mappings - used in fix_metadata.json
            "fix_metadata_lambda_arn": lambdas.get("fix_metadata"),
        }

        # Replace Lambda ARN placeholders with actual ARNs
        for placeholder, lambda_fn in lambda_arn_mappings.items():
            if lambda_fn:
                definition_str = definition_str.replace(
                    f"${{{placeholder}}}", lambda_fn.function_arn
                )

        # Convert back to a dictionary
        return json.loads(definition_str)
