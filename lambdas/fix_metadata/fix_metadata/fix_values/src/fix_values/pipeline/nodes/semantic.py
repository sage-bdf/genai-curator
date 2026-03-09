# This deliverable is considered developed content as defined in contract between BDF parties.


"""Semantic similarity node for metadata correction pipeline."""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import boto3
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.metrics.pairwise import cosine_similarity

from fix_values.pipeline.core.models import (
    CellError,
    CorrectionAttempt,
    CorrectionMethod,
    CorrectionResult,
    PipelineState,
    Schema,
)
from fix_values.pipeline.nodes.base import CorrectionNode, NodeConfig


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def encode(self, texts: List[str], batch_size: int) -> np.ndarray:
        """Encode texts into embeddings.

        Args:
            texts: List of texts to encode
            batch_size: Batch size for encoding

        Returns:
            Array of embeddings
        """
        pass


class SentenceTransformerProvider(EmbeddingProvider):
    """Sentence Transformers embedding provider."""

    def __init__(self, model_name: str):
        """Initialize provider with model name."""
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    async def encode(self, texts: List[str], batch_size: int) -> np.ndarray:
        """Encode texts using sentence transformers."""
        return self.model.encode(texts, batch_size=batch_size, show_progress_bar=False)


class BedrockProvider(EmbeddingProvider):
    """Amazon Bedrock embedding provider."""

    def __init__(self, aws_settings: Optional[Dict[str, str]] = None):
        """Initialize provider with AWS settings."""
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=(
                aws_settings.get("region", "us-east-1") if aws_settings else "us-east-1"
            ),
        )

    async def encode(self, texts: List[str], batch_size: int) -> np.ndarray:
        """Encode texts using Bedrock Titan model."""
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = []
            for text in batch:
                try:
                    response = self.client.invoke_model(
                        modelId="amazon.titan-embed-text-v1",
                        body=json.dumps({"inputText": text}),
                    )
                    embedding = json.loads(response["body"].read())["embedding"]
                    batch_embeddings.append(embedding)
                except Exception as e:
                    logger.error(f"Error getting Bedrock embedding: {e}")
                    # Return zero vector of same size as successful embeddings
                    if batch_embeddings:
                        batch_embeddings.append(np.zeros_like(batch_embeddings[0]))
                    else:
                        # If first in batch failed, skip entire batch
                        logger.error("First embedding in batch failed, skipping batch")
                        break
            embeddings.extend(batch_embeddings)
        return np.array(embeddings)


class SemanticNode(CorrectionNode[List[CellError], List[CorrectionResult]]):
    """Semantic similarity based correction node."""

    def __init__(
        self,
        schema: Schema,
        config: NodeConfig,
        threshold: float = 0.1,
        model_type: str = "sentence-transformers",
        model_name: str = "sentence-transformers/all-mpnet-base-v2",
        batch_size: int = 32,
        aws_settings: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize semantic similarity node.

        Args:
            schema: Metadata schema
            config: Node configuration
            threshold: Minimum similarity threshold
            model_type: Type of embedding model ('sentence-transformers' or 'bedrock')
            model_name: Name of sentence transformer model (if using sentence-transformers)
            batch_size: Batch size for embeddings
            aws_settings: AWS settings for Bedrock (if using bedrock)
        """
        super().__init__(config)
        self.schema = schema
        self.threshold = threshold
        self.batch_size = batch_size
        self.max_concurrency = config.max_concurrency

        # Initialize appropriate embedding provider
        if model_type == "bedrock":
            self.provider = BedrockProvider(aws_settings)
            logger.info("Initialized SemanticNode with Bedrock Titan embeddings")
        else:
            self.provider = SentenceTransformerProvider(model_name)
            logger.info(
                f"Initialized SemanticNode with Sentence Transformers model '{model_name}'"
            )

        self._valid_values_cache: Dict[str, Dict[str, np.ndarray]] = (
            {}
        )  # Cache for valid values embeddings
        self._query_cache: Dict[str, np.ndarray] = {}  # Cache for query embeddings
        logger.info(
            f"Using batch size {batch_size} and max concurrency {self.max_concurrency}"
        )

    def _normalize_value(self, value: Any) -> str:
        """Normalize a value for semantic comparison.

        Args:
            value: Value to normalize

        Returns:
            Normalized string value
        """
        if pd.isna(value):
            return "No Value"
        return str(value)

    async def _get_valid_values_embeddings(
        self, field_name: str, valid_values: List[str]
    ) -> Dict[str, np.ndarray]:
        """Get or compute embeddings for valid field values.

        Args:
            field_name: Field name
            valid_values: List of valid values to embed

        Returns:
            Dictionary mapping valid values to embeddings
        """
        if field_name not in self._valid_values_cache:
            logger.debug(
                f"Computing embeddings for {len(valid_values)} valid values in field '{field_name}'"
            )
            normalized_values = [self._normalize_value(v) for v in valid_values]
            try:
                embeddings = await self.provider.encode(
                    normalized_values, batch_size=self.batch_size
                )
                self._valid_values_cache[field_name] = {
                    str(value): embedding
                    for value, embedding in zip(valid_values, embeddings)
                }
                # Also cache these values in query cache since they're valid values
                for value, embedding in zip(valid_values, embeddings):
                    normalized = self._normalize_value(value)
                    self._query_cache[normalized] = embedding
                logger.debug(f"Cached valid value embeddings for field '{field_name}'")
            except Exception as e:
                logger.error(
                    f"Error computing embeddings for field '{field_name}': {e}"
                )
                return {}
        return self._valid_values_cache[field_name]

    async def _get_query_embedding(self, value: Any) -> Optional[np.ndarray]:
        """Get or compute embedding for a query value.

        Args:
            value: Value to embed

        Returns:
            Embedding array for the value or None if embedding fails
        """
        normalized = self._normalize_value(value)

        # Check if we have this value cached
        if normalized in self._query_cache:
            logger.debug(f"Using cached embedding for query value: {normalized}")
            return self._query_cache[normalized]

        # Compute new embedding if not in cache
        logger.debug(f"Computing new embedding for query value: {normalized}")
        try:
            embeddings = await self.provider.encode([normalized], batch_size=1)
            embedding = embeddings[0]

            # Cache the new embedding
            self._query_cache[normalized] = embedding
            return embedding
        except Exception as e:
            logger.error(f"Error computing embedding for value '{normalized}': {e}")
            return None

    async def _process_batch(
        self,
        errors: List[CellError],
        state: PipelineState,
        semaphore: asyncio.Semaphore,
    ) -> List[Optional[CorrectionResult]]:
        """Process a batch of errors with semantic similarity.

        Args:
            errors: List of errors to process
            state: Current pipeline state
            semaphore: Semaphore for concurrency control

        Returns:
            List of correction results
        """
        async with semaphore:
            try:
                # Group errors by column to process similar fields together
                column_groups: Dict[str, List[Tuple[int, CellError]]] = {}
                for i, error in enumerate(errors):
                    if error.error_type == "vocabulary":
                        field = self.schema.get_field(error.column)
                        if field and field.valid_values:
                            if error.column not in column_groups:
                                column_groups[error.column] = []
                            column_groups[error.column].append((i, error))

                results = [None] * len(errors)  # Initialize with None for all errors

                # Process each column group
                for column, error_group in column_groups.items():
                    field = self.schema.get_field(column)
                    if not field or not field.valid_values:
                        continue

                    try:
                        # Get valid value embeddings from cache
                        valid_embeddings_dict = await self._get_valid_values_embeddings(
                            column, field.valid_values
                        )

                        if not valid_embeddings_dict:
                            logger.error(
                                f"No valid embeddings obtained for column {column}"
                            )
                            continue

                        # Stack valid value embeddings once for the column
                        valid_embeddings = np.stack(
                            [
                                valid_embeddings_dict[value]
                                for value in field.valid_values
                            ]
                        )

                        # Process all errors for this column
                        query_values = []
                        error_indices = []  # Track which errors we're processing
                        for i, (orig_idx, error) in enumerate(error_group):
                            if pd.isna(error.value):
                                logger.info(
                                    f"Processing nan value in column '{error.column}' using 'No Value' representation"
                                )
                                query_values.append("No Value")
                                error_indices.append((i, orig_idx, error))
                            else:
                                query_values.append(str(error.value))
                                error_indices.append((i, orig_idx, error))

                        # Get query embeddings in batch
                        query_embeddings = []
                        valid_error_indices = (
                            []
                        )  # Track which errors have valid embeddings
                        for i, (batch_idx, orig_idx, error) in enumerate(error_indices):
                            embedding = await self._get_query_embedding(query_values[i])
                            if embedding is not None:
                                query_embeddings.append(embedding)
                                valid_error_indices.append((batch_idx, orig_idx, error))
                            else:
                                logger.error(
                                    f"Failed to get embedding for value: {query_values[i]}"
                                )

                        if not query_embeddings:
                            logger.error("No valid query embeddings obtained")
                            continue

                        query_embeddings_stack = np.stack(query_embeddings)

                        # Calculate similarities for all queries at once
                        similarities = cosine_similarity(
                            query_embeddings_stack, valid_embeddings
                        )

                        # Process results for each error
                        for i, (batch_idx, orig_idx, error) in enumerate(
                            valid_error_indices
                        ):
                            try:
                                # Get best match for this error
                                error_similarities = similarities[i]
                                best_idx = error_similarities.argmax()
                                best_score = error_similarities[best_idx]
                                scaled_best_score = round(
                                    float((best_score + 1.0) / 2.0), 3
                                )

                                # Check for ambiguous matches
                                sorted_indices = np.argsort(error_similarities)[
                                    ::-1
                                ]  # Sort in descending order
                                top_scores = error_similarities[
                                    sorted_indices[:2]
                                ]  # Get top 2 scores
                                if (
                                    len(top_scores) > 1
                                    and abs(top_scores[0] - top_scores[1]) < 0.01
                                ):
                                    logger.debug(
                                        f"Skipping ambiguous match for '{error.value}' in column '{error.column}' - "
                                        f"top scores too close: {top_scores[0]:.3f} vs {top_scores[1]:.3f}"
                                    )
                                    results[orig_idx] = None
                                    continue

                                # Only proceed if scaled similarity meets threshold
                                if scaled_best_score >= self.threshold:
                                    best_match = field.valid_values[best_idx]

                                    logger.debug(
                                        f"Found semantic match for '{error.value}' in column '{error.column}': "
                                        f"'{best_match}' (scaled similarity: {scaled_best_score:.3f}, threshold: {self.threshold})"
                                    )

                                    # Create correction attempt
                                    attempt = CorrectionAttempt(
                                        method=CorrectionMethod.SEMANTIC,
                                        row_idx=error.row_idx,
                                        column=error.column,
                                        proposed_value=best_match,
                                        confidence=scaled_best_score,
                                        metadata={
                                            "model": (
                                                "bedrock-titan"
                                                if isinstance(
                                                    self.provider, BedrockProvider
                                                )
                                                else "sentence-transformers"
                                            ),
                                            "similarity_score": scaled_best_score,
                                        },
                                    )

                                    result = CorrectionResult(
                                        error_id=error.id, attempt=attempt, success=True
                                    )

                                    # Update state
                                    error.correction_attempts.append(attempt)
                                    state.correction_history.append(attempt)
                                    state.metadata.at[error.row_idx, error.column] = (
                                        best_match
                                    )

                                    results[orig_idx] = result
                                else:
                                    logger.debug(
                                        f"No semantic match found for '{error.value}' in column '{error.column}' - "
                                        f"best match score {scaled_best_score:.3f} below threshold {self.threshold}"
                                    )
                                    results[orig_idx] = None
                            except Exception as e:
                                logger.error(
                                    f"Error processing {error.column}[{error.row_idx}]: {e}"
                                )
                                results[orig_idx] = None
                    except Exception as e:
                        logger.error(f"Error processing column {column}: {e}")
                        continue

                return results

            except Exception as e:
                logger.error(f"Error processing batch: {e}")
                return [None] * len(errors)

    async def _process_impl(
        self,
        state: PipelineState,
    ) -> Dict[str, Any]:
        """Apply semantic similarity based corrections with batch processing.

        Args:
            state: Current pipeline state containing errors to process

        Returns:
            Dictionary of state updates for LangGraph
        """
        logger.info("[SEMANTIC]")
        logger.info(f"Error Count: {len(state.errors)}")
        logger.info(
            f"Processing {len(state.errors)} errors for semantic similarity correction"
        )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrency)

        # Process errors in batches
        all_results = []
        for i in range(0, len(state.errors), self.batch_size):
            batch = state.errors[i : i + self.batch_size]
            batch_results = await self._process_batch(batch, state, semaphore)
            all_results.extend(batch_results)

        # Filter out None results
        results = [r for r in all_results if r is not None]
        logger.info(
            f"Completed semantic similarity corrections with {len(results)} successful corrections"
        )

        # Return state updates for LangGraph
        return {
            "metadata": state.metadata,
            "errors": state.errors,
            "correction_history": state.correction_history,
            "stats": state.stats,
            "iteration": state.iteration,
        }
