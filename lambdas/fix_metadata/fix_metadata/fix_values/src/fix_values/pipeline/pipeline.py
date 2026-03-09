# This deliverable is considered developed content as defined in contract between BDF parties.


"""Main pipeline implementation for metadata correction."""

from pathlib import Path
from typing import Any, Dict, Union

import pandas as pd
from langfuse.callback import CallbackHandler
from langgraph.graph import END, StateGraph
from loguru import logger

from fix_values.pipeline.core.models import (
    PipelineState,
    Schema,
)
from fix_values.pipeline.core.settings import MetadataCorrectionConfig
from fix_values.pipeline.nodes import (
    FuzzyMatchNode,
    InferenceNode,
    LLMNode,
    NodeConfig,
    SemanticNode,
    ValidationNode,
)
from fix_values.pipeline.schema.loader import load_schema, validate_schema


class MetadataCorrectionPipeline:
    """High-level pipeline interface."""

    def __init__(self, config: MetadataCorrectionConfig) -> None:
        """Initialize pipeline.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self.schema = self._load_schema()
        self.graph = self._build_graph()

    def _load_schema(self) -> Schema:
        """Load and validate schema from configuration."""
        schema = load_schema(
            self.config.pipeline.schema_path, self.config.pipeline.ontology_path
        )
        validate_schema(schema)
        return schema

    def _build_graph(self) -> Any:
        """Construct the pipeline graph."""
        # Create graph with PipelineState schema
        builder = StateGraph(state_schema=PipelineState)

        # Initialize callbacks
        callbacks = [
            CallbackHandler(
                public_key=self.config.langfuse.public_key,
                secret_key=self.config.langfuse.secret_key,
                host=self.config.langfuse.host,
            )
        ]

        # Initial validation node
        validation_node = ValidationNode(
            schema=self.schema,
            config=NodeConfig(name="initial_validation", callbacks=callbacks),
            ignore_fields=self.config.validation.ignore_fields,
        )
        builder.add_node("initial_validation", validation_node.process)

        # Fuzzy matching node
        fuzzy_node = FuzzyMatchNode(
            schema=self.schema,
            config=NodeConfig(name="fuzzy_match"),
            threshold=self.config.fuzzy.threshold,
            max_candidates=self.config.fuzzy.max_candidates,
        )
        builder.add_node("fuzzy_match", fuzzy_node.process)

        # Post-fuzzy validation node
        post_fuzzy_validation = ValidationNode(
            schema=self.schema,
            config=NodeConfig(name="post_fuzzy_validation"),
            ignore_fields=self.config.validation.ignore_fields,
        )
        builder.add_node("post_fuzzy_validation", post_fuzzy_validation.process)

        # Semantic similarity node
        semantic_node = SemanticNode(
            schema=self.schema,
            config=NodeConfig(
                name="semantic_similarity",
                max_concurrency=self.config.semantic.max_concurrency,
            ),
            model_type=self.config.semantic.model_type,
            model_name=self.config.semantic.model_name,
            threshold=self.config.semantic.threshold,
            batch_size=self.config.semantic.batch_size,
        )
        builder.add_node("semantic_similarity", semantic_node.process)

        # Post-semantic validation node
        post_semantic_validation = ValidationNode(
            schema=self.schema,
            config=NodeConfig(name="post_semantic_validation"),
            ignore_fields=self.config.validation.ignore_fields,
        )
        builder.add_node("post_semantic_validation", post_semantic_validation.process)

        # Inference node
        inference_node = InferenceNode(
            schema=self.schema,
            config=NodeConfig(name="inference", callbacks=callbacks),
            min_frequency=self.config.inference.min_frequency,
        )
        builder.add_node("inference", inference_node.process)

        # Post-inference validation node
        post_inference_validation = ValidationNode(
            schema=self.schema,
            config=NodeConfig(name="post_inference_validation"),
            ignore_fields=self.config.validation.ignore_fields,
        )
        builder.add_node("post_inference_validation", post_inference_validation.process)

        # LLM correction node
        llm_node = LLMNode(
            schema=self.schema,
            config=NodeConfig(name="llm_correction", callbacks=callbacks),
            llm_config={
                "model_id": self.config.aws.bedrock_model_id,
                "temperature": self.config.llm.temperature,
                "max_tokens": self.config.llm.max_tokens,
            },
            batch_size=self.config.llm.batch_size,
            batch_mode=self.config.llm.batch_mode,
        )
        builder.add_node("llm_correction", llm_node.process)

        # Final validation node
        final_validation = ValidationNode(
            schema=self.schema,
            config=NodeConfig(name="final_validation"),
            ignore_fields=self.config.validation.ignore_fields,
        )
        builder.add_node("final_validation", final_validation.process)

        # Add edges
        # builder.add_edge("initial_validation", "llm_correction")
        builder.add_edge("initial_validation", "fuzzy_match")
        builder.add_edge("fuzzy_match", "post_fuzzy_validation")
        builder.add_edge("post_fuzzy_validation", "semantic_similarity")
        builder.add_edge("semantic_similarity", "post_semantic_validation")
        builder.add_edge("post_semantic_validation", "inference")
        builder.add_edge("inference", "post_inference_validation")
        builder.add_edge("post_inference_validation", "llm_correction")
        builder.add_edge("llm_correction", "final_validation")
        # builder.add_edge("post_inference_validation", "final_validation")
        builder.add_edge("final_validation", END)

        # Set entry point
        builder.set_entry_point("initial_validation")

        return builder.compile()

    async def process_metadata(self, metadata: pd.DataFrame) -> PipelineState:
        """Process metadata through correction pipeline.

        Args:
            metadata: DataFrame containing records to process

        Returns:
            Final pipeline state after all corrections
        """
        logger.info("[PROCESS METADATA]")
        logger.debug(f"Processing DataFrame with shape {metadata.shape}")

        state = PipelineState(metadata=metadata)
        final_state = await self.graph.ainvoke(state)

        # Convert LangGraph state dict back to PipelineState
        return PipelineState(
            metadata=final_state["metadata"],
            errors=final_state["errors"],
            correction_history=final_state["correction_history"],
            stats=final_state["stats"],
            iteration=final_state["iteration"],
        )

    async def process_batch(
        self, input_dir: Union[str, Path], output_dir: Union[str, Path]
    ) -> Dict[str, PipelineState]:
        """Process a batch of metadata files.

        Args:
            input_dir: Directory containing input CSV files
            output_dir: Directory to write corrected files

        Returns:
            Dictionary mapping filenames to their final pipeline states
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Process each CSV file
        results = {}
        for input_file in input_dir.glob("*.csv"):
            logger.info(f"Processing {input_file}")
            output_file = output_dir / f"{input_file.stem}_corrected.csv"

            try:
                # Read CSV with all columns as strings to prevent type inference
                df = pd.read_csv(input_file, dtype=str)

                # Process entire DataFrame
                state = await self.process_metadata(df)
                results[input_file.name] = state

                # Update DataFrame with corrected values
                for field, values in state.metadata.items():
                    if isinstance(values, list):
                        for idx, value in enumerate(values):
                            df.at[idx, field] = value
                    else:
                        df.at[0, field] = values

                # Write corrected CSV
                df.to_csv(output_file, index=False)
                logger.info(f"Saved corrected file: {output_file}")

            except Exception as e:
                logger.error(f"Error processing {input_file}: {e}")
                continue

        return results
