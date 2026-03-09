# This deliverable is considered developed content as defined in contract between BDF parties.


"""Statistical inference node for metadata correction pipeline."""

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from fix_values.pipeline.core.models import (
    CellError,
    CorrectionAttempt,
    CorrectionMethod,
    CorrectionResult,
    PipelineState,
    Schema,
)
from fix_values.pipeline.nodes.base import CorrectionNode, NodeConfig


class InferenceNode(CorrectionNode[List[CellError], List[CorrectionResult]]):
    """Statistical inference based correction node."""

    def __init__(
        self, schema: Schema, config: NodeConfig, min_frequency: float = 0.8
    ) -> None:
        """Initialize inference node.

        Args:
            schema: Metadata schema
            config: Node configuration
            min_frequency: Minimum relative frequency (0-1) for value to be considered dominant
        """
        super().__init__(config)
        self.schema = schema
        self.min_frequency = min_frequency
        logger.info(f"[{self.config.name}] Initializing InferenceNode:")
        logger.info(f"[{self.config.name}] - Min frequency: {self.min_frequency:.1%}")

    def _find_dominant_value(
        self, df: pd.DataFrame, field: str
    ) -> Optional[Tuple[str, float]]:
        """Find most frequent value that meets threshold.

        Args:
            df: DataFrame containing metadata
            field: Field name to analyze

        Returns:
            Tuple of (dominant value, relative frequency) if found, None otherwise
        """
        logger.info(f"[{self.config.name}] Finding dominant value for field '{field}'")

        # Get value frequencies
        total_rows = len(df)
        value_counts = Counter(df[field].dropna())

        # Calculate relative frequencies
        for value, count in value_counts.most_common():
            rel_freq = count / total_rows
            logger.debug(
                f"[{self.config.name}] Value '{value}' has frequency {rel_freq:.1%} ({count}/{total_rows})"
            )

            if rel_freq >= self.min_frequency:
                logger.info(
                    f"[{self.config.name}] Found dominant value '{value}' with frequency {rel_freq:.1%}"
                )
                return value, rel_freq

        logger.info(
            f"[{self.config.name}] No dominant value found above threshold {self.min_frequency:.1%}"
        )
        return None

    def _infer_correction(
        self, value: str, field: str, df: pd.DataFrame
    ) -> Optional[Tuple[str, float]]:
        """Infer correction based on dominant value.

        Args:
            value: Value to correct
            field: Field name
            df: DataFrame with metadata

        Returns:
            Tuple of (corrected value, confidence) if found
        """
        # Find dominant value
        result = self._find_dominant_value(df, field)
        if not result:
            return None

        dominant_value, frequency = result
        if value != dominant_value:
            logger.info(
                f"[{self.config.name}] Correcting '{value}' to dominant value '{dominant_value}' (frequency: {frequency:.1%})"
            )
            return dominant_value, frequency

        return None

    async def _process_impl(
        self,
        state: PipelineState,
    ) -> Dict[str, Any]:
        """Apply inference based corrections.

        Args:
            state: Current pipeline state containing errors to process

        Returns:
            Dictionary of state updates for LangGraph
        """
        logger.info("[INFERENCE]")
        logger.info(f"Error Count: {len(state.errors)}")
        results: List[CorrectionResult] = []

        # Convert state metadata to DataFrame
        try:
            logger.info(f"[{self.config.name}] Creating DataFrame from metadata")
            logger.debug(f"[{self.config.name}] Metadata type: {type(state.metadata)}")
            if isinstance(state.metadata, pd.DataFrame):
                df = state.metadata
            else:
                logger.debug(f"[{self.config.name}] Converting metadata to DataFrame")
                df = pd.DataFrame([state.metadata])
            logger.debug(f"[{self.config.name}] DataFrame shape: {df.shape}")
            logger.debug(
                f"[{self.config.name}] DataFrame columns: {df.columns.tolist()}"
            )
        except Exception as e:
            logger.error(f"[{self.config.name}] Failed to create DataFrame: {str(e)}")
            logger.error(f"[{self.config.name}] Metadata type: {type(state.metadata)}")
            return {
                "metadata": state.metadata,
                "errors": state.errors,
                "correction_history": state.correction_history,
                "stats": state.stats,
                "iteration": state.iteration,
            }

        for error in state.errors:
            logger.info(
                f"[{self.config.name}] Processing error in column '{error.column}' with value '{error.value}'"
            )
            field = self.schema.get_field(error.column)
            if not field:
                logger.warning(
                    f"[{self.config.name}] No schema field found for column '{error.column}'"
                )
                continue

            # Try to infer correction
            try:
                inferred = self._infer_correction(str(error.value), error.column, df)

                if not inferred:
                    logger.info(
                        f"[{self.config.name}] No correction inferred for value '{error.value}'"
                    )
                    continue
            except Exception as e:
                logger.error(
                    f"[{self.config.name}] Error inferring correction: {str(e)}"
                )
                continue

            value, confidence = inferred

            # Create correction attempt
            attempt = CorrectionAttempt(
                method=CorrectionMethod.INFERENCE,
                row_idx=error.row_idx,
                column=error.column,
                proposed_value=value,
                confidence=confidence,
                metadata={
                    "pattern_frequency": int(
                        df[error.column].value_counts().get(value, 0)
                    )
                },
            )

            result = CorrectionResult(error_id=error.id, attempt=attempt, success=True)
            results.append(result)

            # Update state
            error.correction_attempts.append(attempt)
            state.correction_history.append(attempt)
            state.metadata.at[error.row_idx, error.column] = value

        # Log summary
        logger.info(f"[{self.config.name}] Processed {len(state.errors)} errors")
        logger.info(f"[{self.config.name}] Made {len(results)} corrections")

        # Return state updates for LangGraph
        return {
            "metadata": state.metadata,
            "errors": state.errors,
            "correction_history": state.correction_history,
            "stats": state.stats,
            "iteration": state.iteration,
        }
