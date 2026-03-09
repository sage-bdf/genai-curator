# This deliverable is considered developed content as defined in contract between BDF parties.


from aws_cdk import Stack
from aws_cdk import aws_bedrock as bedrock
from constructs import Construct


class BedrockStack(Stack):
    """Stack for Bedrock resources including Data Automation Projects."""

    def __init__(
        self,
        scope: Construct,
        prefix: str,
        app_name: str,
        **kwargs,
    ) -> None:
        construct_id = f"{prefix}-{app_name}-BedrockStack"
        super().__init__(scope, construct_id, **kwargs)

        # Store prefix and app_name for resource naming
        self.prefix = prefix
        self.app_name = app_name

        # Create a Bedrock Data Automation Project
        self.data_automation_project = bedrock.CfnDataAutomationProject(
            self,
            f"{self.prefix}-{self.app_name}-BDA",
            project_name=f"{self.prefix}-{self.app_name}-BDA",
            project_description="Data Automation Project for extracting metadata from documents",
            # Configure standard output for metadata extraction
            standard_output_configuration=bedrock.CfnDataAutomationProject.StandardOutputConfigurationProperty(
                document=bedrock.CfnDataAutomationProject.DocumentStandardOutputConfigurationProperty(
                    extraction=bedrock.CfnDataAutomationProject.DocumentStandardExtractionProperty(
                        bounding_box=bedrock.CfnDataAutomationProject.DocumentBoundingBoxProperty(
                            state="DISABLED"
                        ),
                        granularity=bedrock.CfnDataAutomationProject.DocumentExtractionGranularityProperty(
                            types=["PAGE", "ELEMENT"]
                        ),
                    ),
                    generative_field=bedrock.CfnDataAutomationProject.DocumentStandardGenerativeFieldProperty(
                        state="ENABLED"
                    ),
                    output_format=bedrock.CfnDataAutomationProject.DocumentOutputFormatProperty(
                        additional_file_format=bedrock.CfnDataAutomationProject.DocumentOutputAdditionalFileFormatProperty(
                            state="DISABLED"
                        ),
                        text_format=bedrock.CfnDataAutomationProject.DocumentOutputTextFormatProperty(
                            types=["MARKDOWN"]
                        ),
                    ),
                )
            ),
        )
