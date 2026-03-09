# This deliverable is considered developed content as defined in contract between BDF parties.


from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from constructs import Construct


class StorageStack(Stack):
    """
    Stack for storage resources including S3 bucket.
    """

    def __init__(self, scope: Construct, prefix: str, app_name: str, **kwargs) -> None:
        construct_id = f"{prefix}-{app_name}-StorageStack"
        super().__init__(scope, construct_id, **kwargs)

        # Store prefix and app_name for resource naming
        self.prefix = prefix
        self.app_name = app_name

        # Create S3 bucket for file storage
        self.bucket = s3.Bucket(
            self,
            f"{self.prefix}-{self.app_name}-Bucket",
            bucket_name=f"{self.prefix}-{self.app_name.lower()}-bucket",
            removal_policy=RemovalPolicy.DESTROY,  # For development; use RETAIN for production
            auto_delete_objects=True,  # For development; remove for production
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.POST,
                    ],
                    allowed_origins=["*"],  # Restrict to specific origins in production
                    allowed_headers=[
                        "Authorization",
                        "Content-Type",
                        "X-Api-Key",
                        "X-Amz-Date",
                        "X-Amz-Security-Token",
                    ],
                )
            ],
            lifecycle_rules=[
                # Default lifecycle rule: expire objects after one week
                s3.LifecycleRule(
                    id="expire-after-one-week",
                    enabled=True,
                    expiration=Duration.days(7),
                    # Apply this rule to all objects except those matching the filters in other rules
                ),
                # Exception rule for files with "schema" prefix
                s3.LifecycleRule(
                    id="preserve-schema-prefix-files",
                    enabled=True,
                    prefix="schema",  # Files starting with "schema"
                    # Set a very long expiration period (100 years) to effectively never expire
                    expiration=Duration.days(36500),
                ),
                # Exception for files in directories containing schema in the name
                s3.LifecycleRule(
                    id="preserve-schema-in-path",
                    enabled=True,
                    prefix="*/schema/",  # Files in */schema/ directories
                    # Set a very long expiration period (100 years) to effectively never expire
                    expiration=Duration.days(36500),
                ),
            ],
        )
