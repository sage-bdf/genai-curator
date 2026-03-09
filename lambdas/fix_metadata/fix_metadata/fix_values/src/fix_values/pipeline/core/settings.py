# This deliverable is considered developed content as defined in contract between BDF parties.


"""Configuration settings for the metadata correction pipeline."""

from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings


class AWSSettings(BaseSettings):
    """AWS configuration settings."""

    aws_region: str = "us-east-1"
    aws_profile: str = "default"
    bedrock_model_id: str = "us.amazon.nova-micro-v1:0"

    class Config:
        env_prefix = "AWS_"


class ValidationSettings(BaseSettings):
    """Schema validation settings."""

    strict_mode: bool = True
    ignore_fields: List[str] = [
        "id",
        "parentId" "createdOn",
        "createdBy",
        "etag",
        "type",
        "benefactorId",
        "currentVersion",
        "dataFileHandleId",
        "eTag",
        "description",
        "comments",
        "Id",
        "experimentId",
        # "readLength",
        # "readDepth",
        # "comments",
        # "dissociationMethod",
        # "age",
        # "eTag",
        # "experimentalTimepoint",
        # "experimentalCondition",
        # "cellType",
        # "dataType",
        # "specimenPreparationMethod",
        # "aliquotID",
        # "timePointUnit",
        # "modelSystemName",
    ]

    class Config:
        env_prefix = "VALIDATION_"


class FuzzyMatchSettings(BaseSettings):
    """Fuzzy matching settings."""

    threshold: float = 0.80
    max_candidates: int = 3

    class Config:
        env_prefix = "FUZZY_"


class SemanticSettings(BaseSettings):
    """Semantic similarity settings."""

    model_type: str = "bedrock"  # Options sentence-transformers or bedrock
    model_name: str = "sentence-transformers/all-mpnet-base-v2"
    batch_size: int = 32
    cache_dir: Optional[Path] = None
    max_concurrency: int = 4  # Maximum number of concurrent error processing tasks
    threshold: float = (
        0.7  # Minimum scaled similarity score (0-1 range) required for a match
    )

    class Config:
        env_prefix = "SEMANTIC_"


class InferenceSettings(BaseSettings):
    """Inference correction settings."""

    min_frequency: float = (
        0.8  # Minimum relative frequency (0-1) for value to be considered dominant
    )

    class Config:
        env_prefix = "INFERENCE_"


class LLMSettings(BaseSettings):
    """LLM correction settings."""

    temperature: float = 0.1
    max_tokens: int = 2000
    stop_sequences: List[str] = []
    cache_responses: bool = True
    batch_size: int = 30  # Number of rows to process in parallel
    batch_mode: str = "combined"  # Options: "parallel" or "combined"

    class Config:
        env_prefix = "LLM_"


class LangfuseSettings(BaseSettings):
    """Langfuse configuration settings."""

    public_key: str = "pk-lf-0ebfea75-6dc9-4849-9cde-fa2810f777c6"
    secret_key: str = "sk-lf-00683ee2-7842-41e0-8560-7dd56d25c262"
    host: str = "http://localhost:3000"

    class Config:
        env_prefix = "LANGFUSE_"


class PipelineSettings(BaseSettings):
    """Global pipeline settings."""

    max_iterations: int = 5
    error_threshold: float = 0.01
    schema_path: Path
    ontology_path: Optional[Path] = None
    output_dir: Path
    log_level: str = "INFO"

    class Config:
        env_prefix = "PIPELINE_"


class MetadataCorrectionConfig(BaseSettings):
    """Complete pipeline configuration."""

    aws: AWSSettings = AWSSettings()
    pipeline: PipelineSettings
    validation: ValidationSettings = ValidationSettings()
    fuzzy: FuzzyMatchSettings = FuzzyMatchSettings()
    semantic: SemanticSettings = SemanticSettings()
    inference: InferenceSettings = InferenceSettings()
    llm: LLMSettings = LLMSettings()
    langfuse: LangfuseSettings = LangfuseSettings()

    class Config:
        env_nested_delimiter = "__"

    @classmethod
    def from_env_file(cls, path: Path) -> "MetadataCorrectionConfig":
        """Load configuration from environment file."""
        return cls.parse_file(path)
