from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class ComputeStack(Stack):
    """Stack for all Lambda functions used in Curator workflows."""

    def __init__(
        self,
        scope: Construct,
        bucket: s3.Bucket,
        prefix: str,
        app_name: str,
        **kwargs,
    ) -> None:
        construct_id = f"{prefix}-{app_name}-ComputeStack"
        super().__init__(scope, construct_id, **kwargs)

        # Store prefix and app_name for resource naming
        self.prefix = prefix
        self.app_name = app_name
        self.bucket = bucket

        # Create all Lambda functions
        self.extract_metadata_lambdas = self._create_extract_metadata_lambdas(bucket)
        self.fix_metadata_lambdas = self._create_fix_metadata_lambdas(bucket)
        self.transform_metadata_lambdas = self._create_transform_metadata_lambdas(
            bucket
        )
        self.utility_lambdas = self._create_utility_lambdas(bucket)

        # Export Lambda ARNs as CloudFormation outputs
        self._export_lambda_arns()

    def _create_lambda_execution_role(self, name: str, description: str) -> iam.Role:
        """Create a Lambda execution role with necessary permissions."""
        role = iam.Role(
            self,
            f"{name}Role",
            role_name=f"{self.prefix}-{self.app_name}-{name}Role",
            description=description,
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Grant permissions to access S3
        self.bucket.grant_read_write(role)

        # Add specific permissions based on Lambda function needs
        return role

    def _create_extract_metadata_lambdas(self, bucket: s3.Bucket) -> dict:
        """Create Lambda functions for the extract_metadata workflow."""
        lambdas = {}
        roles = {}

        # chunk_task Lambda - Used in ChunkTaskLambda state
        lambda_path = "../lambdas/extract_metadata/chunk_task"

        # Create specific role for chunk_task Lambda
        chunk_task_role = self._create_lambda_execution_role(
            "ChunkTaskLambda", "Execution role for the Chunk Task Lambda function"
        )

        # Add specific permissions for chunk_task Lambda
        chunk_task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "states:DescribeExecution",
                    "states:GetExecutionHistory",
                ],
                resources=[
                    f"arn:aws:states:{self.region}:{self.account}:execution:{self.prefix}-{self.app_name}-*:*"
                ],
            )
        )

        roles["chunk_task"] = chunk_task_role

        lambdas["chunk_task"] = lambda_.DockerImageFunction(
            self,
            f"{self.prefix}-{self.app_name}-ChunkTaskLambda",
            function_name=f"{self.prefix}-{self.app_name}-ChunkTaskLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=chunk_task_role,
            environment={
                "LOG_LEVEL": "INFO",
            },
            memory_size=1024,
            timeout=Duration.seconds(300),
        )

        # create_table Lambda - Used in CreateTableFromChunk state
        lambda_path = "../lambdas/extract_metadata/create_table"

        # Create specific role for create_table Lambda
        create_table_role = self._create_lambda_execution_role(
            "CreateTableLambda", "Execution role for the Create Table Lambda function"
        )

        # Add Bedrock model invocation permissions
        create_table_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        roles["create_table"] = create_table_role

        lambdas["create_table"] = lambda_.DockerImageFunction(
            self,
            f"{self.prefix}-{self.app_name}-CreateTableLambda",
            function_name=f"{self.prefix}-{self.app_name}-CreateTableLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=create_table_role,
            environment={
                "LOG_LEVEL": "INFO",
                "LLM_MODEL_ID": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                "MAX_TOKENS": "30000",
            },
            memory_size=1024,
            timeout=Duration.seconds(480),
        )

        # consolidate_results Lambda - Used in ConsolidateResults state
        lambda_path = "../lambdas/extract_metadata/consolidate_results"

        # Create specific role for consolidate_results Lambda
        consolidate_results_role = self._create_lambda_execution_role(
            "ConsolidateResultsLambda",
            "Execution role for the Consolidate Results Lambda function",
        )

        roles["consolidate_results"] = consolidate_results_role

        lambdas["consolidate_results"] = lambda_.DockerImageFunction(
            self,
            f"{self.prefix}-{self.app_name}-ConsolidateResultsLambda",
            function_name=f"{self.prefix}-{self.app_name}-ConsolidateResultsLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=consolidate_results_role,
            environment={
                "LOG_LEVEL": "INFO",
            },
            memory_size=1024,
            timeout=Duration.seconds(300),
        )

        # Store roles for exporting
        lambdas["roles"] = roles

        return lambdas

    def _create_fix_metadata_lambdas(self, bucket: s3.Bucket) -> dict:
        """Create Lambda functions for the fix_metadata workflow."""
        lambdas = {}
        roles = {}

        # fix_metadata Lambda
        lambda_path = "../lambdas/fix_metadata/fix_metadata"

        # Create specific role for fix_metadata Lambda
        fix_metadata_role = self._create_lambda_execution_role(
            "FixMetadataLambda", "Execution role for the Fix Metadata Lambda function"
        )

        # Add Bedrock model invocation permissions
        fix_metadata_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        roles["fix_metadata"] = fix_metadata_role

        lambdas["fix_metadata"] = lambda_.DockerImageFunction(
            self,
            f"{self.prefix}-{self.app_name}-FixMetadataLambda",
            function_name=f"{self.prefix}-{self.app_name}-FixMetadataLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=fix_metadata_role,
            environment={
                "S3_BUCKET": bucket.bucket_name,
                "LOG_LEVEL": "INFO",
            },
            memory_size=1024,
            timeout=Duration.seconds(900),
        )

        # Store roles for exporting
        lambdas["roles"] = roles

        return lambdas

    def _create_transform_metadata_lambdas(self, bucket: s3.Bucket) -> dict:
        """Create Lambda functions for the transform_metadata workflow."""
        lambdas = {}
        roles = {}

        # create_col_translation_tasks Lambda
        lambda_path = "../lambdas/transform_metadata/create_col_translation_tasks"

        # Create specific role for create_col_translation_tasks Lambda
        create_col_translation_tasks_role = self._create_lambda_execution_role(
            "CreateColTranslationTasksLambda",
            "Execution role for the Create Column Translation Tasks Lambda function",
        )

        roles["create_col_translation_tasks"] = create_col_translation_tasks_role

        lambdas["create_col_translation_tasks"] = lambda_.DockerImageFunction(
            self,
            f"{self.prefix}-{self.app_name}-CreateColTranslationTasksLambda",
            function_name=f"{self.prefix}-{self.app_name}-CreateColTranslationTasksLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=create_col_translation_tasks_role,
            environment={
                "S3_BUCKET": bucket.bucket_name,
                "LOG_LEVEL": "INFO",
            },
            memory_size=1024,
            timeout=Duration.seconds(300),
        )

        # translate_col Lambda
        lambda_path = "../lambdas/transform_metadata/translate_col"

        # Create specific role for translate_col Lambda
        translate_col_role = self._create_lambda_execution_role(
            "TranslateColLambda",
            "Execution role for the Translate Column Lambda function",
        )

        # Add Bedrock model invocation permissions
        translate_col_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        roles["translate_col"] = translate_col_role

        lambdas["translate_col"] = lambda_.DockerImageFunction(
            self,
            f"{self.prefix}-{self.app_name}-TranslateColLambda",
            function_name=f"{self.prefix}-{self.app_name}-TranslateColLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=translate_col_role,
            environment={
                "S3_BUCKET": bucket.bucket_name,
                "LOG_LEVEL": "INFO",
                "LLM_MODEL_ID": "amazon.nova-pro-v1:0",
            },
            memory_size=1024,
            timeout=Duration.seconds(300),
        )

        # consolidate_cols Lambda
        lambda_path = "../lambdas/transform_metadata/consolidate_cols"

        # Create specific role for consolidate_cols Lambda
        consolidate_cols_role = self._create_lambda_execution_role(
            "ConsolidateColsLambda",
            "Execution role for the Consolidate Columns Lambda function",
        )

        # Add Bedrock model invocation permissions
        consolidate_cols_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        roles["consolidate_cols"] = consolidate_cols_role

        lambdas["consolidate_cols"] = lambda_.DockerImageFunction(
            self,
            f"{self.prefix}-{self.app_name}-ConsolidateColsLambda",
            function_name=f"{self.prefix}-{self.app_name}-ConsolidateColsLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=consolidate_cols_role,
            environment={
                "S3_BUCKET": bucket.bucket_name,
                "LOG_LEVEL": "INFO",
            },
            memory_size=1024,
            timeout=Duration.seconds(300),
        )

        # Store roles for exporting
        lambdas["roles"] = roles

        return lambdas

    def _create_utility_lambdas(self, bucket: s3.Bucket) -> dict:
        """Create utility Lambda functions used by the API."""
        lambdas = {}
        roles = {}

        # Presigned URL Lambda
        lambda_path = "../lambdas/generate_presigned_url"

        # Create specific role for presigned_url Lambda
        presigned_url_role = self._create_lambda_execution_role(
            "PresignedUrlLambda", "Execution role for the Presigned URL Lambda function"
        )

        roles["presigned_url"] = presigned_url_role

        lambdas["presigned_url"] = lambda_.DockerImageFunction(
            self,
            "PresignedUrlLambda",
            function_name=f"{self.prefix}-{self.app_name}-PresignedUrlLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=presigned_url_role,
            environment={
                "S3_BUCKET": bucket.bucket_name,
            },
        )

        # Task Status Lambda
        lambda_path = "../lambdas/get_task_status"

        # Create specific role for task_status Lambda
        task_status_role = self._create_lambda_execution_role(
            "TaskStatusLambda", "Execution role for the Task Status Lambda function"
        )

        # Add permissions to describe step function executions
        task_status_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "states:DescribeExecution",
                    "states:GetExecutionHistory",
                ],
                resources=[
                    f"arn:aws:states:{self.region}:{self.account}:execution:{self.prefix}-{self.app_name}-*:*"
                ],
            )
        )

        roles["task_status"] = task_status_role

        lambdas["task_status"] = lambda_.DockerImageFunction(
            self,
            "TaskStatusLambda",
            function_name=f"{self.prefix}-{self.app_name}-TaskStatusLambda",
            code=lambda_.DockerImageCode.from_image_asset(lambda_path),
            role=task_status_role,
            environment={
                # State machine ARNs will be set via CloudFormation exports
                # These will be populated during deployment
                "EXTRACT_METADATA_STATE_MACHINE_ARN": "",
                "TABLE_TRANSLATION_STATE_MACHINE_ARN": "",
                "FIX_METADATA_STATE_MACHINE_ARN": "",
            },
        )

        # Store roles for exporting
        lambdas["roles"] = roles

        return lambdas

    def _export_lambda_arns(self) -> None:
        """Export Lambda ARNs as CloudFormation outputs for cross-stack references."""
        # Extract metadata lambdas
        for name, lambda_fn in self.extract_metadata_lambdas.items():
            if name == "roles":
                continue
            # Replace underscores with hyphens for CloudFormation export names
            export_name = name.replace("_", "-")
            CfnOutput(
                self,
                f"ExtractMetadata{name.capitalize()}LambdaArn",
                value=lambda_fn.function_arn,
                export_name=f"{self.prefix}-{self.app_name}-ExtractMetadata-{export_name}-Lambda-Arn",
            )

            # Export role ARN
            role = self.extract_metadata_lambdas["roles"][name]
            CfnOutput(
                self,
                f"ExtractMetadata{name.capitalize()}RoleArn",
                value=role.role_arn,
                export_name=f"{self.prefix}-{self.app_name}-ExtractMetadata-{export_name}-Role-Arn",
            )

        # Fix metadata lambdas
        for name, lambda_fn in self.fix_metadata_lambdas.items():
            if name == "roles":
                continue
            # Replace underscores with hyphens for CloudFormation export names
            export_name = name.replace("_", "-")
            CfnOutput(
                self,
                f"FixMetadata{name.capitalize()}LambdaArn",
                value=lambda_fn.function_arn,
                export_name=f"{self.prefix}-{self.app_name}-FixMetadata-{export_name}-Lambda-Arn",
            )

            # Export role ARN
            role = self.fix_metadata_lambdas["roles"][name]
            CfnOutput(
                self,
                f"FixMetadata{name.capitalize()}RoleArn",
                value=role.role_arn,
                export_name=f"{self.prefix}-{self.app_name}-FixMetadata-{export_name}-Role-Arn",
            )

        # Transform metadata lambdas
        for name, lambda_fn in self.transform_metadata_lambdas.items():
            if name == "roles":
                continue
            # Replace underscores with hyphens for CloudFormation export names
            export_name = name.replace("_", "-")
            CfnOutput(
                self,
                f"TransformMetadata{name.capitalize()}LambdaArn",
                value=lambda_fn.function_arn,
                export_name=f"{self.prefix}-{self.app_name}-TransformMetadata-{export_name}-Lambda-Arn",
            )

            # Export role ARN
            role = self.transform_metadata_lambdas["roles"][name]
            CfnOutput(
                self,
                f"TransformMetadata{name.capitalize()}RoleArn",
                value=role.role_arn,
                export_name=f"{self.prefix}-{self.app_name}-TransformMetadata-{export_name}-Role-Arn",
            )

        # Utility lambdas
        for name, lambda_fn in self.utility_lambdas.items():
            if name == "roles":
                continue
            # Replace underscores with hyphens for CloudFormation export names
            export_name = name.replace("_", "-")
            CfnOutput(
                self,
                f"Utility{name.capitalize()}LambdaArn",
                value=lambda_fn.function_arn,
                export_name=f"{self.prefix}-{self.app_name}-Utility-{export_name}-Lambda-Arn",
            )

            # Export role ARN
            role = self.utility_lambdas["roles"][name]
            CfnOutput(
                self,
                f"Utility{name.capitalize()}RoleArn",
                value=role.role_arn,
                export_name=f"{self.prefix}-{self.app_name}-Utility-{export_name}-Role-Arn",
            )
