#!/usr/bin/env python3

# This deliverable is considered developed content as defined in contract between BDF parties.


import os

from aws_cdk import App, Environment
from stacks.api_stack import ApiStack
from stacks.bedrock_stack import BedrockStack
from stacks.compute_stack import ComputeStack
from stacks.step_functions_stack import StepFunctionsStack
from stacks.storage_stack import StorageStack

APP_NAME = "GenAICurator"

app = App()

# Add prefix logic
prefix = app.node.get_context("prefix")

# Define environment
env = Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT", ""),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

# Create stacks
storage_stack = StorageStack(scope=app, prefix=prefix, app_name=APP_NAME, env=env)

# Create Bedrock stack with Data Automation Project
bedrock_stack = BedrockStack(scope=app, prefix=prefix, app_name=APP_NAME, env=env)

# Create Compute stack with all Lambda functions
compute_stack = ComputeStack(
    scope=app,
    bucket=storage_stack.bucket,
    prefix=prefix,
    app_name=APP_NAME,
    env=env,
)

# Add dependency to ensure Storage stack is created before Compute stack
compute_stack.add_dependency(storage_stack)

# Create Step Functions stack
step_functions_stack = StepFunctionsStack(
    scope=app,
    bucket=storage_stack.bucket,
    bedrock_data_automation_project_arn=bedrock_stack.data_automation_project.attr_project_arn,
    prefix=prefix,
    app_name=APP_NAME,
    env=env,
)

# Add dependencies to ensure prerequisite stacks are created before Step Functions
step_functions_stack.add_dependency(bedrock_stack)
step_functions_stack.add_dependency(compute_stack)

# Create API stack
api_stack = ApiStack(
    scope=app,
    bucket=storage_stack.bucket,
    extract_metadata_state_machine=step_functions_stack.extract_metadata_state_machine,
    table_translation_state_machine=step_functions_stack.table_translation_state_machine,
    fix_metadata_state_machine=step_functions_stack.fix_metadata_state_machine,
    prefix=prefix,
    app_name=APP_NAME,
    env=env,
)

# Add dependencies to ensure prerequisite stacks are created before API
api_stack.add_dependency(step_functions_stack)

app.synth()
